from unittest.mock import MagicMock, patch


def test_deferred_schema_init_uses_injected_factory_and_closes_connection():
    import deferred_runtime
    pg = MagicMock()
    with patch("users.init_user_schema") as init_user, patch("portfolio.init_portfolio_schema") as init_portfolio:
        deferred_runtime.init_deferred_schemas(lambda: pg)
    init_user.assert_called_once_with()
    init_portfolio.assert_called_once_with(pg)
    pg.close.assert_called_once_with()
