"""Terminal UI for managing your GitHub pull request inbox."""

from textual.app import App, ComposeResult
from textual.widgets import Header, Footer, DataTable, LoadingIndicator
from textual.containers import Vertical, VerticalScroll
from textual.binding import Binding
from textual.coordinate import Coordinate
import threading
import webbrowser
from datetime import datetime, timezone
import store
import ghapi
from navigation import NavigationMixin
import comments

STATE_COL = 0
POLL_INTERVAL = 120

STATE_DISPLAY = {
    "unread": "● new",
    "read": "  read",
}

class GhMail(NavigationMixin, App):
    CSS_PATH = "prtui.tcss"

    TITLE = "prtui"
    SUB_TITLE = "GitHub Pull Request Inbox"

    BINDINGS = [
        Binding("q", "quit", "Quit"),
        Binding("r", "mark_read", "Mark Read"),
        Binding("tab", "focus_next_table", "Next Table", show=False, priority=True),
        Binding("shift+tab", "focus_prev_table", "Prev Table", show=False, priority=True),
        Binding("o", "open_pr", "Open in Browser"),
        Binding("enter", "toggle_comments", "Comments", priority=True),
    ]

    def compose(self) -> ComposeResult:
        yield Header()
        yield LoadingIndicator()
        yield Vertical(
            DataTable(id="prs"),
            DataTable(id="reviewer"),
            DataTable(id="requested"),
            id="tables",
        )
        yield VerticalScroll(id="comments")
        yield Footer()

    def on_mount(self) -> None:
        threading.Thread(target=self._fetch_worker, daemon=True).start()
        self.set_interval(POLL_INTERVAL, self._poll_updates)

    def _fetch_worker(self) -> None:
        """Fetch/update PRs and refresh tables."""
        try:
            show_loading = not store.has_data()
            if show_loading:
                self.call_from_thread(self._show_loading, True)
            try:
                ghapi.poll_for_updates(
                    on_progress=lambda msg: self.call_from_thread(
                        self.notify, msg)
                )
            finally:
                if show_loading:
                    self.call_from_thread(self._show_loading, False)
            self.prs = {
                "prs": store.get_pull_requests("mine"),
                "reviewer": store.get_pull_requests("reviewer"),
                "requested": store.get_pull_requests("requested"),
            }
            self.call_from_thread(self._populate_tables)
        except Exception as e:
            self.call_from_thread(self.notify, f"Fetch failed: {e}",
                                  severity="error")

    def _poll_updates(self) -> None:
        """Periodically check for PR changes and refresh tables."""
        def worker():
            try:
                changed = ghapi.poll_for_updates(
                    on_progress=lambda msg: self.call_from_thread(
                        self.notify, msg)
                )
                if changed:
                    self.prs = {
                        "prs": store.get_pull_requests("mine"),
                        "reviewer": store.get_pull_requests("reviewer"),
                        "requested": store.get_pull_requests("requested"),
                    }
                    self.call_from_thread(self._populate_tables, True)
            except Exception as e:
                self.call_from_thread(self.notify, f"Poll failed: {e}",
                                      severity="error")
        threading.Thread(target=worker, daemon=True).start()

    def _show_loading(self, show: bool) -> None:
        self.query_one(LoadingIndicator).display = show

    def _populate_tables(self, preserve_focus=False) -> None:
        # Save focus state before clearing
        focused_id = None
        focused_row = 0
        if preserve_focus:
            try:
                table = self._focused_table()
                focused_id = table.id
                focused_row = table.cursor_row
            except Exception:
                pass

        for table_id, prs in self.prs.items():
            table = self.query_one(f"#{table_id}", DataTable)
            table.clear(columns=True)
            table.cursor_type = "row"
            table.zebra_stripes = True
            table.add_columns("State", "Repo", "Title", "Author", "Approvals", "CI")
            for pr in prs:
                ci = "✓" if pr["jenkins_approved"] else ""
                approvals = str(pr["approval_count"]) if pr["approval_count"] else ""
                if pr.get("my_approved"):
                    approvals = f"✓ {approvals}".strip()
                table.add_row(
                    STATE_DISPLAY[pr["state"]],
                    pr["repo"],
                    pr["title"],
                    pr["author"],
                    approvals,
                    ci,
                    key=f"{pr['repo']}#{pr['number']}",
                )

        # Restore focus or default to first table
        if focused_id:
            table = self.query_one(f"#{focused_id}", DataTable)
            row = min(focused_row, table.row_count - 1)
            if row >= 0:
                table.move_cursor(row=row)
            table.focus()
        else:
            self.query_one("#prs", DataTable).focus()

    @staticmethod
    def _get_pr_key(table):
        """Return (repo, number) from the cursor row's key."""
        row_key, _ = table.coordinate_to_cell_key(table.cursor_coordinate)
        return row_key.value.rsplit("#", 1)

    def action_mark_read(self) -> None:
        table = self._focused_table()
        row = table.cursor_row
        prs = self.prs.get(table.id or "", [])
        repo, number = self._get_pr_key(table)
        store.mark_read(repo, number)
        prs[row]["state"] = "read"
        prs[row]["read_at"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        table.update_cell_at(Coordinate(row, STATE_COL), STATE_DISPLAY["read"])
        panel = self.query_one("#comments", VerticalScroll)
        if panel.display:
            comments.populate_panel(panel, repo, number, prs[row]["read_at"])

    def _selected_pr_key(self):
        """Return (repo, number) for the currently selected PR row."""
        table = self._focused_table()
        if table.row_count == 0:
            return None
        return self._get_pr_key(table)

    def _hide_comments(self) -> None:
        panel = self.query_one("#comments", VerticalScroll)
        panel.display = False
        self.query_one(f"#{self._comments_source}", DataTable).focus()

    def _show_comments(self) -> None:
        key = self._selected_pr_key()
        if not key:
            return
        repo, number = key
        self._comments_source = self._focused_table().id or "prs"
        table = self._focused_table()
        prs = self.prs.get(table.id or "", [])
        read_at = prs[table.cursor_row].get("read_at")
        panel = self.query_one("#comments", VerticalScroll)
        comments.populate_panel(panel, repo, number, read_at)
        panel.display = True
        panel.focus()

    def action_toggle_comments(self) -> None:
        if self.query_one("#comments", VerticalScroll).display:
            self._hide_comments()
        else:
            self._show_comments()

    def action_open_pr(self) -> None:
        key = self._selected_pr_key()
        if not key:
            return
        repo, number = key
        webbrowser.open(store.get_pr_url(repo, number))


if __name__ == "__main__":
    GhMail().run()
