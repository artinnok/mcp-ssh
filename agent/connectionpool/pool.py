import logging
import threading
import time
from .connection import Connection
from .connection import ConnectionState

class ConnectionPool:
    def __init__(self, connection_configs, reconnection_delay=5):
        """
        Initialize the connection pool.

        :param connection_configs: List of connection configurations.
        :param reconnection_delay: Delay in seconds between reconnection attempts (default: 5 seconds).
        """
        self.reconnection_delay = reconnection_delay
        self.connections = []
        self.os_info_cache = {}
        self.lock = threading.Lock()  # For thread-safe access to os_info_cache
        self._monitor_lock = threading.Lock()  # To ensure one monitor loop at a time
        self._stopping = threading.Event()  # To signal stop
        self._timer = None
        self._started = False

        for config in connection_configs:
            connection = Connection(config)
            self.connections.append(connection)

    def gather_os_info(self, connection):
        """Gather OS info from the remote host over SSH."""
        with self.lock:
            if connection.get_state() != ConnectionState.OPEN:
                return
            try:
                result = connection.execute("uname -srm")
                if result.exit_code == 0 and result.stdout.strip():
                    self.os_info_cache[connection.name] = result.stdout.strip()
                else:
                    logging.warning(
                        f"⚠️ Failed to gather OS info on {connection.name} "
                        f"(exit={result.exit_code}, stderr={result.stderr.strip()})"
                    )
            except Exception as e:
                logging.error(f"❌ Failed to gather OS info for {connection.name}: {e}")

    def start(self):
        if self._started:
            logging.warning("⚠️ Connection pool already started.")
            return
        self._started = True
        logging.info("🚀 Starting the connection pool...")

        for connection in self.connections:
            connection.open()
            self.gather_os_info(connection)

        self._schedule_monitor()

    def _schedule_monitor(self):
        if not self._stopping.is_set():
            self._timer = threading.Timer(self.reconnection_delay, self._monitor_once)
            self._timer.start()

    def _monitor_once(self):
        with self._monitor_lock:
            if self._stopping.is_set():
                return

            if not self.connections:
                logging.info("🔍 No connections in the pool.")
            else:
                closed_found = False
                for connection in self.connections:
                    if connection.get_state() != ConnectionState.OPEN:
                        closed_found = True
                        logging.warning(f"⚠️ Connection {connection.name} is down. Attempting to reconnect...")
                        connection.open()
                        self.gather_os_info(connection)

                if closed_found:
                    logging.info("🔁 One or more connections were re-opened.")
                else:
                    logging.info("✅ All connections are currently open.")

        self._schedule_monitor()

    def stop(self):
        if not self._started:
            logging.warning("⚠️ Connection pool not started or already stopped.")
            return

        logging.info("🛑 Stopping the connection pool...")
        self._stopping.set()

        if self._timer:
            self._timer.cancel()
            self._timer = None

        with self._monitor_lock:
            pass  # Wait for any running monitor to complete

        for connection in self.connections:
            connection.close()

        self._started = False

    def query_pool(self):
        with self.lock:
            pool_state = []
            for connection in self.connections:
                conn_state = connection.get_state()
                state = {
                    "name": connection.name,
                    "is_running": conn_state == ConnectionState.OPEN,
                    "os_info": self.os_info_cache.get(connection.name, "No OS info cached"),
                    "connection_state": conn_state.value,
                }
                pool_state.append(state)
            return pool_state

    def send_command(self, connection_name, command):
        with self.lock:
            for connection in self.connections:
                if connection.name == connection_name:
                    try:
                        return connection.execute(command)
                    except Exception as e:
                        logging.error(f"❌ Failed to execute command on {connection_name}: {e}")
                        return None
            logging.warning(f"⚠️ Connection {connection_name} not found.")
            return None

    def expose_pool_state(self):
        return self.query_pool()