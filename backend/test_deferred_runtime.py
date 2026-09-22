from unittest.mock import patch


def test_deferred_schema_init_keeps_only_retained_user_schema():
    import deferred_runtime
    with patch("users.init_user_schema") as init_user:
        deferred_runtime.init_deferred_schemas(lambda: None)
    init_user.assert_called_once_with()
