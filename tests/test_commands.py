from unittest import mock

from elasticsearch.exceptions import TransportError

from elasticsearch_django.management.commands import (
    BaseSearchCommand,
    create_search_index,
    delete_search_index,
    prune_search_index,
    rebuild_search_index,
    update_search_index,
)


class BaseSearchCommandTests:
    """Tests for the elasticsearch_django management commands base command."""

    @mock.patch("elasticsearch_django.management.commands.logger")
    @mock.patch.object(BaseSearchCommand, "do_index_command")
    def test_handle(self, mock_do, mock_log):
        """Test the main handle method calls do_index_command."""
        obj = BaseSearchCommand()
        obj.handle(indexes=["foo", "bar"])
        # this should have called the do_index_command twice
        mock_do.assert_has_calls([mock.call("foo"), mock.call("bar")])
        mock_do.reset_mock()
        mock_do.side_effect = TransportError(
            123, "oops", {"error": {"reason": "no idea"}}
        )
        obj.handle(indexes=["baz"])
        mock_do.assert_called_once_with("baz")
        mock_log.exception.assert_called_once()


class NamedCommandTests:
    """Test each named command."""

    @mock.patch(
        "elasticsearch_django.management.commands.create_search_index.create_index"
    )
    def test_create_search_index(self, mock_create):
        """Test the create_search_index command."""
        cmd = create_search_index.Command()
        cmd.do_index_command("foo")
        mock_create.assert_called_once_with("foo")

    @mock.patch(
        "elasticsearch_django.management.commands.delete_search_index.delete_index"
    )
    def test_delete_search_index(self, mock_delete):
        """Test the delete_search_index command."""
        cmd = delete_search_index.Command()
        retval = cmd.do_index_command(
            "foo", interactive=False
        )  # True would hang the tests
        assert retval == mock_delete.return_value
        mock_delete.assert_called_once_with("foo")
        mock_delete.reset_mock()

        # mock out thw raw_input so the test doesn't hang
        with mock.patch.object(
            delete_search_index.Command, "_confirm_action"
        ) as mock_confirm:
            mock_confirm.return_value = False
            retval = cmd.do_index_command("foo", interactive=True)
            mock_delete.assert_not_called()
            assert retval is None

    @mock.patch(
        "elasticsearch_django.management.commands.prune_search_index.prune_index"
    )
    def test_prune_search_index(self, mock_prune):
        """Test the prune_search_index command."""
        cmd = prune_search_index.Command()
        cmd.do_index_command("foo")
        mock_prune.assert_called_once_with("foo")

    @mock.patch(
        "elasticsearch_django.management.commands.update_search_index.update_index"
    )
    def test_update_search_index(self, mock_update):
        """Test the update_search_index command."""
        cmd = update_search_index.Command()
        cmd.do_index_command("foo")
        mock_update.assert_called_once_with("foo")

    @mock.patch(
        "elasticsearch_django.management.commands.rebuild_search_index.delete_index"
    )
    @mock.patch(
        "elasticsearch_django.management.commands.rebuild_search_index.create_index"
    )
    @mock.patch(
        "elasticsearch_django.management.commands.rebuild_search_index.update_index"
    )
    def test_rebuild_search_index(self, mock_update, mock_create, mock_delete):
        """Test the rebuild_search_index command."""
        cmd = rebuild_search_index.Command()
        result = cmd.do_index_command(
            "foo", interactive=False
        )  # True would hang the tests
        mock_delete.assert_called_once_with("foo")
        mock_create.assert_called_once_with("foo")
        mock_update.assert_called_once_with("foo")
        assert result["delete"] == mock_delete.return_value
        assert result["create"] == mock_create.return_value
        assert result["update"] == mock_update.return_value
        # check that the delete is handled if the index does not exist
        mock_delete.side_effect = TransportError("Index not found")
        result = cmd.do_index_command(
            "foo", interactive=False
        )  # True would hang the tests
        assert result["delete"] == {}
