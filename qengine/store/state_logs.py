class LogsState:
    def __init__(self) -> None:
        self.errors = []
        self.info = []

    def add(self, message: str, log_type: str = 'info'):
        """Add a categorized log entry for backtest results."""
        from qengine.store import store
        import qengine.helpers as jh
        self.info.append({
            'id': jh.generate_unique_id(),
            'session_id': store.app.session_id,
            'timestamp': jh.now_to_timestamp(),
            'message': str(message),
            'type': log_type,
        })
