from __future__ import annotations

from scripts.sync_idl import sync


def test_sync_idl_generates_and_preserves_unchanged_service(tmp_path) -> None:
    idl_dir = tmp_path / "idl"
    output_dir = tmp_path / "generated"
    idl_dir.mkdir()
    idl = idl_dir / "user.thrift"
    idl.write_text("service UserService { string get_user(1: string user_id) }", encoding="utf-8")

    assert sync(idl_dir, output_dir) == {"created": 1, "updated": 0, "unchanged": 0}
    target = output_dir / "user_user_service_api.py"
    generated = target.read_text(encoding="utf-8")
    assert "def get_user(self, user_id: Any = None)" in generated
    assert sync(idl_dir, output_dir) == {"created": 0, "updated": 0, "unchanged": 1}
    idl.write_text("service UserService { string get_user(1: string user_id) bool delete_user() }", encoding="utf-8")
    assert sync(idl_dir, output_dir) == {"created": 0, "updated": 1, "unchanged": 0}
    assert "def delete_user(self)" in target.read_text(encoding="utf-8")

