from shared.config.database.engine import engine


def test_engine_enables_connection_health_checks():
    assert engine.sync_engine.pool._pre_ping is True
    assert engine.sync_engine.pool._recycle == 300
