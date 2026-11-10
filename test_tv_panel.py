"""Тесты для tv-panel.py — запуск: python test_tv_panel.py

Проверяют логику работы с конфигом, запуск adb и построение GUI
(с подменой subprocess, чтобы не трогать реальные телевизоры).
"""
import importlib.util
import json
import os
import tempfile
import unittest
from unittest import mock
from types import ModuleType
from types import SimpleNamespace
from typing import cast

HERE = os.path.dirname(os.path.abspath(__file__))

# --- импортируем модуль с дефисом в имени (обычный import невозможен) ---
spec = importlib.util.spec_from_file_location("tv_panel", os.path.join(HERE, "tv-panel.py"))
if spec is None or spec.loader is None:
    raise ImportError("Could not load tv-panel.py")
tv_panel = cast(ModuleType, importlib.util.module_from_spec(spec))
spec.loader.exec_module(tv_panel)


class FakeCompleted:
    def __init__(self, returncode=0, stdout="", stderr=""):
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr



class TestConfig(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self._old = tv_panel.CONFIG
        self._old_legacy = tv_panel.LEGACY_CONFIG
        setattr(tv_panel, "CONFIG", os.path.join(self.tmp.name, "tv-panel.json"))
        setattr(tv_panel, "LEGACY_CONFIG", os.path.join(self.tmp.name, "legacy.json"))

    def tearDown(self):
        setattr(tv_panel, "CONFIG", self._old)
        setattr(tv_panel, "LEGACY_CONFIG", self._old_legacy)
        self.tmp.cleanup()

    def test_defaults_when_no_file(self):
        self.assertEqual(tv_panel.load_config(), tv_panel.DEFAULTS)
        self.assertTrue(all(not tv["address"] for tv in tv_panel.DEFAULTS))
        self.assertEqual(
            [tv["name"] for tv in tv_panel.DEFAULTS],
            ["Телевизор 1", "Телевизор 2"],
        )

    def test_adb_path_uses_application_resources(self):
        self.assertTrue(os.path.isfile(tv_panel.ADB))

    def test_broken_json_returns_defaults(self):
        with open(tv_panel.CONFIG, "w", encoding="utf-8") as f:
            f.write("{ not json ]")
        self.assertEqual(tv_panel.load_config(), tv_panel.DEFAULTS)

    def test_roundtrip(self):
        data = [{"name": "A", "address": "1.1.1.1:1"}, {"name": "B", "address": "2.2.2.2:2"}]
        tv_panel.save_config(data)
        self.assertEqual(tv_panel.load_config(), data)

    def test_non_list_returns_defaults(self):
        with open(tv_panel.CONFIG, "w", encoding="utf-8") as f:
            json.dump({"name": "x"}, f)
        self.assertEqual(tv_panel.load_config(), tv_panel.DEFAULTS)

    def test_single_entry_preserves_tv_and_fills_second_default(self):
        only_tv = {"name": "Only", "address": "1.1.1.1:1"}
        tv_panel.save_config([only_tv])
        self.assertEqual(tv_panel.load_config(), [only_tv])

    def test_multiple_custom_devices_are_not_truncated(self):
        devices = [
            {"name": f"TV {index}", "address": f"192.168.0.{index}:5555"}
            for index in range(1, 5)
        ]
        tv_panel.save_config(devices)
        self.assertEqual(tv_panel.load_config(), devices)

    def test_empty_list_is_a_valid_empty_configuration(self):
        tv_panel.save_config([])
        self.assertEqual(tv_panel.load_config(), [])

    def test_legacy_config_is_loaded_when_user_config_is_missing(self):
        legacy = [{"name": "Legacy", "address": "192.168.0.2:5555"}]
        with open(tv_panel.LEGACY_CONFIG, "w", encoding="utf-8") as f:
            json.dump(legacy, f)
        self.assertEqual(tv_panel.load_config(), legacy)

    def test_save_creates_parent_directory(self):
        setattr(tv_panel, "CONFIG", os.path.join(self.tmp.name, "nested", "config.json"))
        data = [{"name": "TV", "address": "192.168.0.1:5555"}]
        tv_panel.save_config(data)
        self.assertEqual(tv_panel.load_config(), data)

    def test_invalid_entry_returns_defaults(self):
        tv_panel.save_config(["not a TV"])
        self.assertEqual(tv_panel.load_config(), tv_panel.DEFAULTS)

    def test_save_is_utf8_and_readable(self):
        tv_panel.save_config([{"name": "Телевизор", "address": "1.1.1.1:1"}])
        with open(tv_panel.CONFIG, "r", encoding="utf-8") as f:
            self.assertIn("Телевизор", f.read())

    def test_parse_mdns_services_returns_tls_serials_and_tcp_addresses(self):
        output = (
            "List of discovered mDNS services\n"
            "adb-serial-1 _adb-tls-connect._tcp 192.168.0.10:43000\n"
            "192.168.0.11:5555 _adb._tcp 192.168.0.11:5555\n"
            "pairing._adb-tls-pairing._tcp 192.168.0.12:43001\n"
        )
        self.assertEqual(
            tv_panel.parse_mdns_services(output),
            [
                {"name": "Android TV (192.168.0.10:43000)", "address": "adb-serial-1._adb-tls-connect._tcp"},
                {"name": "Android TV (192.168.0.11:5555)", "address": "192.168.0.11:5555"},
            ],
        )



class TestAdbCalls(unittest.TestCase):
    """Проверяем, что run_adb строит правильную команду и обрабатывает ошибки."""

    def _make_card(self, index=0):
        root = tv_panel.tk.Tk()
        root.withdraw()
        card = tv_panel.TVCard(root, index, {"name": "T", "address": "10.0.0.1:5555"}, lambda: None)
        return root, card

    def test_run_adb_success_builds_correct_command(self):
        root, card = self._make_card()
        try:
            with mock.patch.object(tv_panel.subprocess, "run", return_value=FakeCompleted(0, "ok")) as m:
                ok = card.run_adb(["shell", "input", "keyevent", "26"], "Готово")
            self.assertTrue(ok)
            args = m.call_args[0][0]
            self.assertEqual(args[0], tv_panel.ADB)
            self.assertEqual(args[1:3], ["-s", "10.0.0.1:5555"])
            self.assertEqual(card.status.get(), "Готово")
        finally:
            root.destroy()

    def test_run_adb_empty_address(self):
        root, card = self._make_card()
        try:
            card.address.set("")
            with mock.patch.object(tv_panel.subprocess, "run") as m:
                ok = card.run_adb(["shell", "getprop"])
            self.assertFalse(ok)
            m.assert_not_called()
            self.assertEqual(card.status.get(), "Не указан адрес")
        finally:
            root.destroy()

    def test_run_adb_nonzero_exit_shows_last_line(self):
        root, card = self._make_card()
        try:
            res = FakeCompleted(1, "", "error: device offline\nsecond line")
            with mock.patch.object(tv_panel.subprocess, "run", return_value=res):
                ok = card.run_adb(["shell", "true"])
            self.assertFalse(ok)
            self.assertEqual(card.status.get(), "second line")
        finally:
            root.destroy()

    def test_keyevent_passes_keycode(self):
        root, card = self._make_card()
        try:
            with mock.patch.object(tv_panel.subprocess, "run", return_value=FakeCompleted(0, "ok")) as m:
                card.keyevent("26")
            args = m.call_args[0][0]
            self.assertIn("26", args)
            self.assertIn("keyevent", args)
        finally:
            root.destroy()

    def test_connect_calls_adb_connect(self):
        root, card = self._make_card()
        try:
            res = FakeCompleted(0, "connected to 10.0.0.1:5555")
            with mock.patch.object(tv_panel.subprocess, "run", return_value=res) as m:
                ok = card.connect()
            self.assertTrue(ok)
            self.assertEqual(m.call_args[0][0], [tv_panel.ADB, "connect", "10.0.0.1:5555"])
            self.assertIn("connected", card.status.get())
        finally:
            root.destroy()

    def test_connect_failure_is_not_reported_as_success(self):
        root, card = self._make_card()
        try:
            res = FakeCompleted(0, "", "failed to connect to 10.0.0.1:5555")
            with mock.patch.object(tv_panel.subprocess, "run", return_value=res):
                ok = card.connect()
            self.assertFalse(ok)
            self.assertIn("failed to connect", card.status.get())
        finally:
            root.destroy()

    def test_connect_empty_address_does_not_run_adb(self):
        root, card = self._make_card()
        try:
            card.address.set("")
            with mock.patch.object(tv_panel.subprocess, "run") as run:
                ok = card.connect()
            self.assertFalse(ok)
            run.assert_not_called()
            self.assertEqual(card.status.get(), "Не указан адрес")
        finally:
            root.destroy()

    def test_connect_uses_discovered_tls_service_serial(self):
        root, card = self._make_card()
        try:
            card.address.set("adb-serial._adb-tls-connect._tcp")
            with mock.patch.object(
                tv_panel.subprocess,
                "run",
                return_value=FakeCompleted(0, "device"),
            ) as run:
                self.assertTrue(card.connect())
            self.assertEqual(
                run.call_args.args[0],
                [tv_panel.ADB, "-s", "adb-serial._adb-tls-connect._tcp", "get-state"],
            )
        finally:
            root.destroy()

    def test_mi_home_button_is_not_shown(self):
        root = tv_panel.tk.Tk()
        root.withdraw()
        try:
            c0 = tv_panel.TVCard(root, 0, {"name": "A", "address": "a:1"}, lambda: None)
            c1 = tv_panel.TVCard(root, 1, {"name": "B", "address": "b:1"}, lambda: None)
            t0 = [w.cget("text") for w in c0.winfo_children() if isinstance(w, tv_panel.ttk.Button)]
            t1 = [w.cget("text") for w in c1.winfo_children() if isinstance(w, tv_panel.ttk.Button)]
            self.assertNotIn("Mi Home", t0)
            self.assertNotIn("Mi Home", t1)
        finally:
            root.destroy()

    def test_view_missing_scrcpy_shows_error(self):
        root, card = self._make_card()
        try:
            with mock.patch.object(tv_panel.subprocess, "Popen", side_effect=FileNotFoundError()):
                with mock.patch.object(tv_panel.messagebox, "showerror") as showerror:
                    card.view()
            showerror.assert_called_once()
        finally:
            root.destroy()

    def test_view_empty_address_shows_status(self):
        root, card = self._make_card()
        try:
            card.address.set("")
            with mock.patch.object(tv_panel.subprocess, "Popen") as popen:
                card.view()
            popen.assert_not_called()
            self.assertEqual(card.status.get(), "Не указан адрес")
        finally:
            root.destroy()

    def test_view_opens_in_fullscreen_when_requested(self):
        root, card = self._make_card()
        try:
            with mock.patch.object(tv_panel.subprocess, "Popen") as popen:
                card.view(fullscreen=True)
            args = popen.call_args.args[0]
            self.assertIn("--fullscreen", args)
            self.assertIn("--window-borderless", args)
            self.assertEqual(card.status.get(), "Полноэкранный просмотр запущен")
        finally:
            root.destroy()

    def test_regular_view_does_not_force_fullscreen(self):
        root, card = self._make_card()
        try:
            with mock.patch.object(tv_panel.subprocess, "Popen") as popen:
                card.view()
            args = popen.call_args.args[0]
            self.assertNotIn("--fullscreen", args)
            self.assertEqual(card.status.get(), "Окно просмотра запущено")
        finally:
            root.destroy()


class TestGuiSmoke(unittest.TestCase):
    """Собираем всё приложение целиком и проверяем, что виджеты на месте."""

    def test_app_builds(self):
        with tempfile.TemporaryDirectory() as tmp:
            old_config = tv_panel.CONFIG
            setattr(tv_panel, "CONFIG", os.path.join(tmp, "tv-panel.json"))
            self.addCleanup(setattr, tv_panel, "CONFIG", old_config)

            app = tv_panel.App()
            app.withdraw()
            try:
                self.assertEqual(len(app.cards), 2)
                self.assertEqual(app.title(), "Управление Android TV")
                header_labels = [
                    widget.cget("text")
                    for widget in app.winfo_children()[0].winfo_children()
                    if isinstance(widget, (tv_panel.ttk.Label, tv_panel.tk.Label))
                ]
                self.assertIn("Панель управления", header_labels)
                subtitle = next(
                    widget
                    for widget in app.winfo_children()[0].winfo_children()
                    if widget.cget("text") == "Android TV  ·  ADB и удалённый просмотр"
                )
                self.assertEqual(
                    subtitle.cget("foreground"),
                    tv_panel.COLORS["subtitle"],
                )
                app.save()
                for card in app.cards:
                    self.assertEqual(card.status.get(), "Настройки сохранены")
            finally:
                app.destroy()

    def test_mousewheel_scrolls_list_and_accumulates_small_deltas(self):
        with tempfile.TemporaryDirectory() as tmp:
            old_config = tv_panel.CONFIG
            setattr(tv_panel, "CONFIG", os.path.join(tmp, "tv-panel.json"))
            self.addCleanup(setattr, tv_panel, "CONFIG", old_config)

            app = tv_panel.App()
            app.withdraw()
            try:
                with mock.patch.object(app.canvas, "yview_scroll") as scroll:
                    first = app.on_mousewheel(SimpleNamespace(widget=app.cards[0], delta=60, num=0))
                    self.assertEqual(first, "break")
                    scroll.assert_not_called()
                    second = app.on_mousewheel(SimpleNamespace(widget=app.cards[0], delta=60, num=0))
                    self.assertEqual(second, "break")
                    scroll.assert_called_once_with(-1, "units")
            finally:
                app.destroy()

    def test_mousewheel_does_not_scroll_when_pointer_is_outside_list(self):
        with tempfile.TemporaryDirectory() as tmp:
            old_config = tv_panel.CONFIG
            setattr(tv_panel, "CONFIG", os.path.join(tmp, "tv-panel.json"))
            self.addCleanup(setattr, tv_panel, "CONFIG", old_config)

            app = tv_panel.App()
            app.withdraw()
            try:
                with mock.patch.object(app.canvas, "yview_scroll") as scroll:
                    result = app.on_mousewheel(
                        SimpleNamespace(widget=app, delta=120, num=0)
                    )
                self.assertIsNone(result)
                scroll.assert_not_called()
            finally:
                app.destroy()

    def test_linux_wheel_buttons_scroll_in_expected_directions(self):
        with tempfile.TemporaryDirectory() as tmp:
            old_config = tv_panel.CONFIG
            setattr(tv_panel, "CONFIG", os.path.join(tmp, "tv-panel.json"))
            self.addCleanup(setattr, tv_panel, "CONFIG", old_config)

            app = tv_panel.App()
            app.withdraw()
            try:
                with mock.patch.object(app.canvas, "yview_scroll") as scroll:
                    app.on_mousewheel(SimpleNamespace(widget=app.canvas, delta=0, num=4))
                    app.on_mousewheel(SimpleNamespace(widget=app.canvas, delta=0, num=5))
                self.assertEqual(scroll.call_args_list[0].args, (-1, "units"))
                self.assertEqual(scroll.call_args_list[1].args, (1, "units"))
            finally:
                app.destroy()

    def test_add_and_remove_devices_preserves_other_card_edits(self):
        with tempfile.TemporaryDirectory() as tmp:
            old_config = tv_panel.CONFIG
            setattr(tv_panel, "CONFIG", os.path.join(tmp, "tv-panel.json"))
            self.addCleanup(setattr, tv_panel, "CONFIG", old_config)

            app = tv_panel.App()
            app.withdraw()
            try:
                app.cards[0].name.set("Renamed TV")
                app.add_tv({"name": "Third TV", "address": "192.168.0.3:5555"})
                self.assertEqual(len(app.cards), 3)
                self.assertEqual(app.cards[0].name.get(), "Renamed TV")
                app.remove_tv(1)
                self.assertEqual(len(app.cards), 2)
                self.assertEqual([card.name.get() for card in app.cards], ["Renamed TV", "Third TV"])
                self.assertTrue(app.save(update_status=False))
                self.assertEqual(tv_panel.load_config(), [card.values() for card in app.cards])
            finally:
                app.destroy()

    def test_discovery_adds_only_new_devices_and_preserves_edits(self):
        with tempfile.TemporaryDirectory() as tmp:
            old_config = tv_panel.CONFIG
            setattr(tv_panel, "CONFIG", os.path.join(tmp, "tv-panel.json"))
            self.addCleanup(setattr, tv_panel, "CONFIG", old_config)

            app = tv_panel.App()
            app.withdraw()
            app.cards[0].address.set("adb-existing._adb-tls-connect._tcp")
            app.cards[0].name.set("Existing")
            output = (
                "List of discovered mDNS services\n"
                "adb-existing _adb-tls-connect._tcp 192.168.0.10:43000\n"
                "adb-new _adb-tls-connect._tcp 192.168.0.11:43001\n"
            )
            try:
                with mock.patch.object(
                    tv_panel.subprocess,
                    "run",
                    return_value=FakeCompleted(0, output),
                ):
                    app.discover_devices()
                self.assertEqual(len(app.cards), 3)
                self.assertEqual(app.cards[0].name.get(), "Existing")
                self.assertEqual(app.cards[2].device(), "adb-new._adb-tls-connect._tcp")
            finally:
                app.destroy()

if __name__ == "__main__":
    unittest.main(verbosity=2)
