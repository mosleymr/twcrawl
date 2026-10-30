import copy
import json
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from twcrawl import crawler
from twcrawl.parser import parse_high_scores
from twcrawl.server import make_server
from twcrawl.storage import archive_data, compare_crawls, latest_run, read_runs
from twcrawl.telnet import TelnetError, TelnetSession


MENU = "<F> Poker Run\nSelection (? for menu): "
XML = "<TWGSData><Games>" + "".join(
    f"<Game><ID><GameSlot>{letter}</GameSlot><GameName>Game {letter}</GameName></ID>"
    "<GeneralInfo><GameAge>1 Days</GameAge><ClosedGame>False</ClosedGame></GeneralInfo>"
    "<Dynamic><ActivePlayers>1</ActivePlayers></Dynamic></Game>" for letter in "AFZ"
) + "</Games></TWGSData>"


def score(position, name):
    return f"{position:<4}{'100':>10}{'0':>11} {'**':<3}{name:<31}Merchant Cruiser"


SCORES = "Trade Wars 2002 Trader Rankings\n--- ----- -- ----- -----\n" + score(1, "Alice") + "\n"


class FakeSession:
    def __init__(self, *args, **kwargs):
        self.text = ""
        self.host = "fake"
        self.port = 2002
        self.last = ""

    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass

    def send_line(self, command=""):
        self.last = command
        if command == "$":
            self.text += XML + MENU
        elif command == "H":
            self.text += SCORES + "Enter your choice:"
        elif command == "#":
            self.text += "Players Online\nNode 1 Game A : Alice\n" + MENU
        elif command in "AFZ" and command:
            self.text += "Enter your choice:"
        else:
            self.text += MENU

    def wait_for(self, pattern, since=None, **kwargs):
        return self.text[since or 0:]


def fixture():
    return {"generated_at": "2026-10-01T00:00:00+00:00", "servers": [{
        "server_id": "1", "name": "Test Server", "slug": "test", "telnet": "test:2002",
        "status": "online", "crawl_complete": True, "games": [{
            "letter": "A", "name": "SubZero", "bigbang": "10/01/2026", "status": "ok",
            "high_scores_checked_at": "first", "high_scores": [{"name": "Alice"}], "stats": {"Latency": "100 ms"},
        }], "online_check": {"status": "ok", "checked_at": "first", "players": [
            {"letter": "A", "player": "Alice", "node": 1, "location": "Game A"},
        ]},
    }]}


class ProtocolTests(unittest.TestCase):
    def test_split_ansi_and_crlf_at_every_boundary(self):
        source = "hello\x1b[1;34m world\x1b[0m\r\nnext\x1b]0;title\x07!"
        for index in range(len(source) + 1):
            session = TelnetSession("unused", 23)
            self.assertEqual(session._clean_text(source[:index]) + session._clean_text(source[index:]),
                             "hello world\nnext!")

    def test_all_high_score_pages_are_kept(self):
        result = parse_high_scores(SCORES + "[Pause]\n\n" + score(2, "Bob") + "\nEnter your choice:")
        self.assertEqual([p["name"] for p in result["high_scores"]], ["Alice", "Bob"])

    def test_xml_trailing_prompt_need_not_repeat_game_list(self):
        session = FakeSession()
        session.text = "Selection (? for menu): "
        _, info = crawler.wait_for_server_menu(session, since=0, timeout=1, require_games=False)
        self.assertFalse(info.get("menu_games"))

    def crawl_fake(self, partial=False):
        def menu(session, **kwargs):
            if partial and session.last == "X":
                raise TelnetError("menu timed out")
            return MENU, {"menu_games": [{"letter": "F", "name": "Poker Run"}]}

        with patch.object(crawler, "TelnetSession", FakeSession), patch.object(crawler, "wait_for_server_menu", side_effect=menu), \
                patch("twcrawl.online.wait_for_players_online", side_effect=lambda t, **kw: t.text[kw["since"]:]):
            return crawler.crawl_server({"telnet": "fake:2002"})

    def test_xml_letters_override_incomplete_ansi_menu(self):
        result = self.crawl_fake()
        self.assertEqual([g["letter"] for g in result["games"]], list("AFZ"))
        self.assertEqual(result["online_check"]["players"][0]["letter"], "A")
        self.assertTrue(all(g.get("high_scores_checked_at") for g in result["games"]))

    def test_menu_return_timeout_does_not_discard_xml_games(self):
        result = self.crawl_fake(partial=True)
        self.assertEqual(result["game_count"], 3)
        self.assertEqual(result["twgs_xml"]["game_count"], 3)
        self.assertFalse(result["crawl_complete"])
        self.assertTrue(crawler.needs_current_data({**result, "status": "online"}))

    def test_previous_xml_server_does_not_collapse_to_menu(self):
        with patch.object(crawler, "TelnetSession", FakeSession), \
                patch.object(crawler, "wait_for_server_menu", return_value=(MENU, {"menu_games": [{"letter": "F"}]})), \
                patch.object(crawler, "fetch_twgs_xml", return_value={}):
            with self.assertRaisesRegex(TelnetError, "retaining prior games"):
                crawler.crawl_server({"telnet": "fake:2002", "twgs_xml": {"game_count": 20}})

    def test_failed_crawl_retains_rosters_and_marks_online_unknown(self):
        data = fixture()
        with patch.object(crawler, "crawl_server", side_effect=TelnetError("offline")):
            crawler.crawl_servers(data)
        self.assertEqual(data["servers"][0]["games"][0]["high_scores"], [{"name": "Alice"}])
        self.assertEqual(data["servers"][0]["online_check"]["status"], "error")


class StorageTests(unittest.TestCase):
    def test_archive_and_historical_reports_are_immutable(self):
        with tempfile.TemporaryDirectory() as directory:
            db = Path(directory) / "history.sqlite3"
            first = archive_data(fixture(), db, kind="import")
            current = copy.deepcopy(first)
            game = current["servers"][0]["games"][0]
            game["high_scores"].append({"name": "Bob"})
            game["high_scores_checked_at"] = "second"
            current["servers"][0]["online_check"] = {"status": "error", "checked_at": "second", "players": []}
            second = archive_data(current, db)
            self.assertEqual(second["latest_report"]["new_players"][0]["player"]["name"], "Bob")
            self.assertEqual(second["latest_report"]["no_longer_online"], [])
            self.assertEqual(len(read_runs(db)), 2)
            self.assertEqual(read_runs(db, run_id=1)[0]["data"], first)
            self.assertEqual(latest_run(db)["data"], second)

    def test_rebang_does_not_report_every_player_as_new(self):
        old = fixture()
        current = copy.deepcopy(old)
        game = current["servers"][0]["games"][0]
        game.update(bigbang="10/05/2026", high_scores=[{"name": "Bob"}], high_scores_checked_at="second")
        report = compare_crawls(old, current)
        self.assertEqual(len(report["rebanged_games"]), 1)
        self.assertEqual(report["new_players"], [])

    def test_failed_server_is_not_reported_as_game_removal(self):
        old = fixture()
        current = copy.deepcopy(old)
        current["servers"][0].update(status="error", games=[])
        self.assertEqual(compare_crawls(old, current)["removed_games"], [])

    def test_first_online_sample_is_a_baseline_not_a_join(self):
        old = fixture()
        old["servers"][0].pop("online_check")
        self.assertEqual(compare_crawls(old, fixture())["newly_online"], [])

    def test_changed_nodes_do_not_report_presence_changes(self):
        old = fixture()
        current = copy.deepcopy(old)
        check = current["servers"][0]["online_check"]
        check["checked_at"] = "second"
        check["players"][0]["node"] = 10
        report = compare_crawls(old, current)
        self.assertEqual(report["newly_online"], [])
        self.assertEqual(report["no_longer_online"], [])

    def test_http_reads_database_for_both_mtc_and_extensionless_routes(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            db = root / "test.sqlite3"
            archive_data(fixture(), db)
            server = make_server("127.0.0.1", 0, database=db, out=root, api_only=True)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            base = f"http://127.0.0.1:{server.server_port}"
            def get(endpoint):
                with urlopen(base + endpoint) as response:
                    return json.load(response)
            try:
                with patch.object(TelnetSession, "connect", side_effect=AssertionError("HTTP must not crawl")):
                    self.assertEqual(get("/api/games.json"), get("/api/games"))
                    self.assertEqual(len(get("/api/games?player=alice&q=SubZero")["games"]), 1)
                    self.assertEqual(get("/api/online?player=alice")["session_count"], 1)
                    self.assertEqual(get("/api/servers/1/games/a.json")["name"], "SubZero")
                    self.assertEqual(get("/api/runs/1/report")["run_id"], 1)
                    current = fixture()
                    current["servers"][0]["games"][0]["name"] = "Updated"
                    archive_data(current, db)
                    self.assertEqual(get("/api/games.json")["games"][0]["name"], "Updated")
                    self.assertEqual(len(get("/api/runs?limit=1")["runs"]), 1)
                    with self.assertRaises(HTTPError) as caught:
                        urlopen(Request(base + "/api/games", data=b"{}"))
                    self.assertEqual(caught.exception.code, 405)
                    caught.exception.close()
                    with self.assertRaises(HTTPError) as caught:
                        get("/api/runs?limit=nope")
                    self.assertEqual(caught.exception.code, 400)
                    caught.exception.close()
            finally:
                server.shutdown()
                server.server_close()
                thread.join()


if __name__ == "__main__":
    unittest.main()
