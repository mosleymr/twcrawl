import copy
import json
import importlib.util
import tempfile
import threading
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from twcrawl import crawler
from twcrawl.parser import normalize_game_date, parse_game_stats, parse_high_scores, parse_twgs_xml
from twcrawl.repair import repair_reports
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
        current["generated_at"] = "2026-10-05T12:00:00+00:00"
        game = current["servers"][0]["games"][0]
        game.update(bigbang="10/05/2026", high_scores=[{"name": "Bob"}], high_scores_checked_at="second")
        report = compare_crawls(old, current)
        self.assertEqual(len(report["rebanged_games"]), 1)
        self.assertEqual(report["new_players"], [])

    def test_date_format_changes_and_unchanged_old_dates_are_not_rebangs(self):
        old = fixture()
        current = copy.deepcopy(old)
        current["generated_at"] = "2026-11-16T17:00:00+00:00"
        for value in ("10/01/2026", "2026-10-01", "10/1/26"):
            current["servers"][0]["games"][0]["bigbang"] = value
            self.assertEqual(compare_crawls(old, current)["rebanged_games"], [])

    def test_old_corrected_backward_and_future_dates_are_not_rebangs(self):
        old = fixture()
        old["generated_at"] = "2026-11-15T17:00:00+00:00"
        current = copy.deepcopy(old)
        current["generated_at"] = "2026-11-16T17:00:00+00:00"
        for value in ("10/02/2026", "09/30/2026", "10/01/2054"):
            game = current["servers"][0]["games"][0]
            game.update(bigbang=value, high_scores_checked_at="second", high_scores=[{"name": "Bob"}])
            report = compare_crawls(old, current)
            self.assertEqual(report["rebanged_games"], [])
            self.assertEqual(report["new_players"], [])

    def test_real_reset_after_an_offline_gap_and_timezone_boundary_is_reported(self):
        old = fixture()
        old["generated_at"] = "2026-11-16T00:00:00+00:00"
        old["servers"][0].update(status="error", last_success_at="2026-10-01T12:00:00+00:00")
        current = copy.deepcopy(old)
        current["generated_at"] = "2026-11-17T00:05:00+00:00"
        current["servers"][0].update(status="online", last_success_at=current["generated_at"])
        for value in ("11/01/2026", "11/16/2026"):
            current["servers"][0]["games"][0]["bigbang"] = value
            self.assertEqual(len(compare_crawls(old, current)["rebanged_games"]), 1)

    def test_shifted_year_records_are_compared_using_capture_date_and_age(self):
        old = fixture()
        old["generated_at"] = "2026-11-15T17:00:00+00:00"
        game = old["servers"][0]["games"][0]
        game.update(bigbang="03/27/2054", days_open=233, stats={"Start Day": "03/27/54", "Game Age": "233 Days"})
        current = copy.deepcopy(old)
        current["generated_at"] = "2026-11-16T17:00:00+00:00"
        current["servers"][0]["games"][0].update(bigbang="03/27/2026", days_open=234,
            stats={"Start Day": "03/27/54", "Game Age": "234 Days", "Local Game Time": "11/16/54 12:00 PM"})
        self.assertEqual(compare_crawls(old, current)["rebanged_games"], [])
        # An offline retained record must not advance its date with today's year.
        current["servers"][0].update(status="error", last_success_at=current["generated_at"])
        with tempfile.TemporaryDirectory() as directory:
            current["generated_at"] = "2027-11-16T17:00:00+00:00"
            saved = archive_data(current, Path(directory) / "test.sqlite3")
            self.assertEqual(saved["servers"][0]["games"][0]["bigbang"], "03/27/2026")

    def test_failed_roster_and_whitespace_are_not_new_players(self):
        old = fixture()
        current = copy.deepcopy(old)
        game = current["servers"][0]["games"][0]
        game.update(high_scores_checked_at="second", high_scores=[{"name": "  ALICE  "}])
        self.assertEqual(compare_crawls(old, current)["new_players"], [])
        game.update(high_scores_error="incomplete", high_scores=[{"name": "Bob"}])
        self.assertEqual(compare_crawls(old, current)["new_players"], [])

    def test_crawler_connections_are_excluded_from_activity_and_deltas(self):
        old = fixture()
        current = copy.deepcopy(old)
        check = current["servers"][0]["online_check"]
        check.update(checked_at="second", players=[{"player": " TWCrawl ", "letter": "A"},
                                                   {"player": "Alice", "letter": "A"}])
        report = compare_crawls(old, current)
        self.assertEqual(report["newly_online"], [])
        self.assertEqual(report["activity"]["session_count"], 1)

    def test_unknown_replacement_date_does_not_establish_new_player_joins(self):
        current = fixture()
        current["servers"][0]["games"][0].update(bigbang="", high_scores_checked_at="second",
                                                high_scores=[{"name": "Bob"}])
        self.assertEqual(compare_crawls(fixture(), current)["new_players"], [])

    def test_repair_preserves_newer_local_edits(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            db, data_path = root / "history.sqlite3", root / "crawl.json"
            stored = archive_data(fixture(), db)
            stored.update(generated_at="2026-11-17T12:00:00+00:00")
            stored["servers"].append({"server_id": "local", "name": "Locally Added", "games": []})
            data_path.write_text(json.dumps(stored))
            repair_reports(db, data_path, apply=True)
            saved = json.loads(data_path.read_text())
            self.assertEqual(saved["servers"][1]["name"], "Locally Added")
            self.assertEqual(saved["generated_at"], stored["generated_at"])

    def test_repair_is_backed_up_idempotent_and_preserves_raw_captures(self):
        import sqlite3
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            db, data_path = root / "history.sqlite3", root / "crawl.json"
            archive_data(fixture(), db)
            current = fixture()
            current["generated_at"] = "2026-11-16T17:00:00+00:00"
            game = current["servers"][0]["games"][0]
            game.update(bigbang="03/27/2054", stats={"Start Day": "03/27/54", "Game Age": "234 Days"},
                        raw_xml="original capture", raw_stats="original stats")
            # Simulate an archive written by the old parser.
            with sqlite3.connect(db) as connection:
                current.update(run_id=2, latest_report={"rebanged_games": [game]})
                connection.execute("INSERT INTO runs VALUES (2, ?, ?, 'crawl', ?, ?)",
                    (current["generated_at"], current["generated_at"], json.dumps(current), json.dumps(current["latest_report"])))
            data_path.write_text(json.dumps(current))
            before = db.read_bytes(), data_path.read_bytes()
            preview = repair_reports(db, data_path)
            self.assertFalse(preview["applied"])
            self.assertEqual((db.read_bytes(), data_path.read_bytes()), before)
            result = repair_reports(db, data_path, apply=True)
            self.assertTrue(Path(result["backup"]).joinpath(db.name).exists())
            self.assertEqual(len(read_runs(db)), 2)
            saved = latest_run(db)["data"]
            self.assertEqual(saved["run_id"], 2)
            self.assertEqual(saved["servers"][0]["games"][0]["raw_xml"], "original capture")
            self.assertEqual(saved["servers"][0]["games"][0]["raw_stats"], "original stats")
            self.assertEqual(saved["servers"][0]["games"][0]["bigbang"], "03/27/2026")
            self.assertEqual(saved["latest_report"]["rebanged_games"], [])
            self.assertEqual(json.loads(data_path.read_text()), saved)
            second = repair_reports(db, data_path, apply=True)
            self.assertEqual(second["runs_changed"], 0)
            self.assertIsNone(second["backup"])


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


class GameDateTests(unittest.TestCase):
    def test_xml_with_and_without_local_clock_has_identical_real_date(self):
        crawl = datetime(2026, 11, 16, 17, tzinfo=timezone.utc)
        for clock in ("", "<Dynamic><LocalGameTime>11/16/54 12:00 PM</LocalGameTime></Dynamic>"):
            xml = ("<TWGSData><Server><ServerLocalTime>11/16/2026 12:00 PM</ServerLocalTime></Server><Games>"
                   "<Game><ID><GameSlot>B</GameSlot><GameName>Dragon Slayer</GameName></ID>"
                   "<GeneralInfo><StartDay>03/27/54</StartDay><GameAge>234 Days</GameAge></GeneralInfo>"
                   + clock + "</Game></Games></TWGSData>")
            self.assertEqual(parse_twgs_xml(xml, crawl)["xml_games"][0]["bigbang"], "03/27/2026")

    def test_age_anchor_rollover_and_invalid_dates(self):
        crawl = datetime(2026, 1, 1, tzinfo=timezone.utc)
        self.assertEqual(normalize_game_date("12/31/53", None, crawl, game_age=1), "12/31/2025")
        self.assertEqual(normalize_game_date("12/31/99", 0, crawl), "12/31/2025")
        self.assertEqual(normalize_game_date("01/01/2026", None, crawl), "01/01/2026")
        for value in ("13/01/26", "01/00/26", "02/30/26"):
            self.assertEqual(normalize_game_date(value, None, crawl, game_age=1), "")

    def test_star_stats_without_clock_use_same_age_anchor(self):
        result = parse_game_stats("Game Stats:\nStart Day = 03/27/54\nGame Age = 234 Days\nEnd Stats.",
                                  datetime(2026, 11, 16, tzinfo=timezone.utc))
        self.assertEqual(result["bigbang"], "03/27/2026")


class DeploymentTests(unittest.TestCase):
    def test_activity_page_is_built_without_embedding_crawl_data(self):
        from twcrawl.render import build_site
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            build_site(fixture(), output)
            page = (output / "active.html").read_text()
            self.assertIn('id="run-select"', page)
            self.assertNotIn("Alice", page)
            self.assertTrue((output / "assets" / "twcrawl-active.js").is_file())
            self.assertTrue((output / "assets" / "twcrawl-active.css").is_file())

    def test_activity_publisher_preserves_existing_site_and_backs_up_page(self):
        root = Path(__file__).resolve().parents[1]
        spec = importlib.util.spec_from_file_location("publish_active", root / "deploy" / "publish-active.py")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            checkout, public = base / "checkout", base / "htdocs"
            web = checkout / "src" / "twcrawl" / "web"
            web.mkdir(parents=True)
            (public / "games").mkdir(parents=True)
            for name in ("active.html", "twcrawl-active.css", "twcrawl-active.js"):
                (web / name).write_text("new " + name)
            (public / "games" / "style.css").write_text("existing style")
            (public / "index.html").write_text("existing index")
            (public / "active.html").write_text("previous page")
            module.publish(checkout, public)
            self.assertEqual((public / "active.html").read_text(), "new active.html")
            self.assertEqual((public / "index.html").read_text(), "existing index")
            self.assertEqual((public / "games" / "style.css").read_text(), "existing style")
            self.assertEqual(next((checkout / "data" / "logs").glob("active-backup-*/active.html")).read_text(), "previous page")

    def test_proxy_is_added_only_to_the_named_virtual_host(self):
        path = Path(__file__).resolve().parents[1] / "deploy" / "apache-setup.py"
        spec = importlib.util.spec_from_file_location("apache_setup", path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        other = "<VirtualHost *:443>\nServerName other.example\n</VirtualHost>\n"
        source = other + "<VirtualHost *:443>\nServerName roguetw.net:443\nSSLEngine on\n</VirtualHost>\n"
        result = module.add_include(source, "roguetw.net")
        self.assertTrue(result.startswith(other))
        self.assertEqual(result.count('Include "conf/extra/twcrawl-api.conf"'), 1)
        self.assertEqual(module.add_include(result, "roguetw.net"), result)
        with self.assertRaises(ValueError):
            module.add_include(source, "absent.example")
        self.assertEqual(module.enable_module("#LoadModule proxy_module modules/mod_proxy.so\n", "proxy_module"),
                         "LoadModule proxy_module modules/mod_proxy.so\n")


if __name__ == "__main__":
    unittest.main()
