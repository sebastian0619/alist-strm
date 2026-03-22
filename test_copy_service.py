from services.copy_service import CopyService


def test_copy_service_uses_declared_settings_fields():
    service = CopyService()
    service.settings.copy_source_dir = "/source"
    service.settings.copy_target_dir = "/target"
    service.settings.copy_replace_dir = "/mnt"

    assert service._has_copy_paths() is True
    assert service.settings.copy_source_dir == "/source"
    assert service.settings.copy_target_dir == "/target"
    assert service.settings.copy_replace_dir == "/mnt"
