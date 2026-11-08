import unittest
from unittest.mock import Mock

from bleak.exc import BleakError

from avea.avea import (
    Bulb,
    FIRMWARE_REVISION_UUID,
    HARDWARE_REVISION_UUID,
    MANUFACTURER_NAME_UUID,
    SERIAL_NUMBER_UUID,
    check_bounds,
)


class FirmwareClient:
    def __init__(self, payload=None, error=None):
        self.payload = payload
        self.error = error
        self.uuid = None
        self.is_connected = True

    async def read_gatt_char(self, uuid):
        self.uuid = uuid
        if self.error:
            raise self.error
        return self.payload

    async def stop_notify(self, uuid):
        return None

    async def disconnect(self):
        self.is_connected = False


class LoggingTests(unittest.IsolatedAsyncioTestCase):
    def test_check_bounds_logs_invalid_string(self):
        with self.assertLogs("avea.avea", level="WARNING") as logs:
            self.assertEqual(check_bounds("abc"), 0)

        self.assertIn("was not a number", "\n".join(logs.output))

    def test_check_bounds_logs_none(self):
        with self.assertLogs("avea.avea", level="WARNING") as logs:
            self.assertEqual(check_bounds(None), 0)

        self.assertIn("was not a number", "\n".join(logs.output))

    async def test_read_firmware_version_logs_bleak_error(self):
        bulb = Bulb("00:11:22:33:44:55")
        bulb._client = FirmwareClient(error=BleakError("read failed"))

        with self.assertLogs("avea.avea", level="WARNING") as logs:
            self.assertEqual(await bulb._read_firmware_version(), "")

        self.assertIn("Could not read firmware version", "\n".join(logs.output))

    async def test_read_firmware_version_logs_decode_error(self):
        bulb = Bulb("00:11:22:33:44:55")
        bulb._client = FirmwareClient(payload=bytearray(b"\xff"))

        with self.assertLogs("avea.avea", level="WARNING") as logs:
            self.assertEqual(await bulb._read_firmware_version(), "")

        self.assertIn("Could not decode firmware version", "\n".join(logs.output))

    async def test_read_firmware_version_strips_trailing_nul(self):
        bulb = Bulb("00:11:22:33:44:55")
        bulb._client = FirmwareClient(
            payload=bytearray(b"firmware-version\x00ignored\x00")
        )

        self.assertEqual(await bulb._read_firmware_version(), "firmware-version")

    def test_get_fw_version_formats_app_version(self):
        bulb = Bulb("00:11:22:33:44:55")
        bulb._client = FirmwareClient(payload=bytearray(b"1.1.2.328Bf"))

        self.assertEqual(bulb.get_fw_version(), "1.1.2 (328)")
        self.assertEqual(bulb.fw_version, "1.1.2 (328)")
        self.assertEqual(bulb._client.uuid, FIRMWARE_REVISION_UUID)
        bulb.close()

    def test_get_fw_version_formats_numeric_build(self):
        bulb = Bulb("00:11:22:33:44:55")
        bulb._client = FirmwareClient(payload=bytearray(b"1.1.2.328"))

        self.assertEqual(bulb.get_fw_version(), "1.1.2 (328)")
        bulb.close()

    def test_get_fw_version_keeps_unknown_format(self):
        bulb = Bulb("00:11:22:33:44:55")
        bulb._client = FirmwareClient(payload=bytearray(b"firmware-version"))

        self.assertEqual(bulb.get_fw_version(), "firmware-version")
        self.assertEqual(bulb.fw_version, "firmware-version")
        bulb.close()

    def test_process_name_notification_strips_trailing_nul(self):
        bulb = Bulb("00:11:22:33:44:55")

        bulb.process_notification(b"\x58test-bulb\x00ignored\x00")

        self.assertEqual(bulb.name, "test-bulb")

    def test_process_name_notification_logs_decode_error(self):
        bulb = Bulb("00:11:22:33:44:55")
        bulb.name = "Previous name"

        with self.assertLogs("avea.avea", level="WARNING") as logs:
            bulb.process_notification(b"\x58\xff")

        self.assertIn("Could not decode bulb name notification", "\n".join(logs.output))
        self.assertEqual(bulb.name, "Unknown")

    async def test_read_serial_number_reads_expected_uuid(self):
        bulb = Bulb("00:11:22:33:44:55")
        bulb._client = FirmwareClient(payload=bytearray(b"ABC123\x00"))

        self.assertEqual(await bulb._read_serial_number(), "ABC123")
        self.assertEqual(bulb._client.uuid, SERIAL_NUMBER_UUID)

    async def test_read_serial_number_strips_extra_nuls(self):
        bulb = Bulb("00:11:22:33:44:55")
        bulb._client = FirmwareClient(payload=bytearray(b"ABC123\x00\x00"))

        self.assertEqual(await bulb._read_serial_number(), "ABC123")

    async def test_read_serial_number_strips_at_first_nul(self):
        bulb = Bulb("00:11:22:33:44:55")
        bulb._client = FirmwareClient(payload=bytearray(b"ABC123\x00junk"))

        self.assertEqual(await bulb._read_serial_number(), "ABC123")

    async def test_read_serial_number_logs_bleak_error(self):
        bulb = Bulb("00:11:22:33:44:55")
        bulb._client = FirmwareClient(error=BleakError("read failed"))

        with self.assertLogs("avea.avea", level="WARNING") as logs:
            self.assertEqual(await bulb._read_serial_number(), "")

        self.assertIn("Could not read serial number", "\n".join(logs.output))

    async def test_read_serial_number_logs_decode_error(self):
        bulb = Bulb("00:11:22:33:44:55")
        bulb._client = FirmwareClient(payload=bytearray(b"\xff"))

        with self.assertLogs("avea.avea", level="WARNING") as logs:
            self.assertEqual(await bulb._read_serial_number(), "")

        self.assertIn("Could not decode serial number", "\n".join(logs.output))

    def test_get_serial_number_caches_result(self):
        bulb = Bulb("00:11:22:33:44:55")
        bulb._client = FirmwareClient(payload=bytearray(b"ABC123"))

        self.assertEqual(bulb.get_serial_number(), "ABC123")
        self.assertEqual(bulb.serial_number, "ABC123")
        self.assertEqual(bulb._client.uuid, SERIAL_NUMBER_UUID)
        bulb.close()

    def test_get_serial_number_returns_empty_when_connection_fails(self):
        bulb = Bulb("00:11:22:33:44:55")
        bulb.serial_number = "Unknown"
        bulb.connect = Mock(return_value=False)

        self.assertEqual(bulb.get_serial_number(), "")
        self.assertEqual(bulb.serial_number, "")

    async def test_read_hardware_revision_reads_expected_uuid(self):
        bulb = Bulb("00:11:22:33:44:55")
        bulb._client = FirmwareClient(payload=bytearray(b"revision\x00ignored"))

        self.assertEqual(await bulb._read_hardware_revision(), "revision")
        self.assertEqual(bulb._client.uuid, HARDWARE_REVISION_UUID)

    async def test_read_hardware_revision_logs_bleak_error(self):
        bulb = Bulb("00:11:22:33:44:55")
        bulb._client = FirmwareClient(error=BleakError("read failed"))

        with self.assertLogs("avea.avea", level="WARNING") as logs:
            self.assertEqual(await bulb._read_hardware_revision(), "")

        self.assertIn("Could not read hardware revision", "\n".join(logs.output))

    async def test_read_hardware_revision_logs_decode_error(self):
        bulb = Bulb("00:11:22:33:44:55")
        bulb._client = FirmwareClient(payload=bytearray(b"\xff"))

        with self.assertLogs("avea.avea", level="WARNING") as logs:
            self.assertEqual(await bulb._read_hardware_revision(), "")

        self.assertIn("Could not decode hardware revision", "\n".join(logs.output))

    async def test_read_manufacturer_name_reads_expected_uuid(self):
        bulb = Bulb("00:11:22:33:44:55")
        bulb._client = FirmwareClient(payload=bytearray(b"manufacturer\x00ignored"))

        self.assertEqual(await bulb._read_manufacturer_name(), "manufacturer")
        self.assertEqual(bulb._client.uuid, MANUFACTURER_NAME_UUID)

    async def test_read_manufacturer_name_logs_bleak_error(self):
        bulb = Bulb("00:11:22:33:44:55")
        bulb._client = FirmwareClient(error=BleakError("read failed"))

        with self.assertLogs("avea.avea", level="WARNING") as logs:
            self.assertEqual(await bulb._read_manufacturer_name(), "")

        self.assertIn("Could not read manufacturer name", "\n".join(logs.output))

    async def test_read_manufacturer_name_logs_decode_error(self):
        bulb = Bulb("00:11:22:33:44:55")
        bulb._client = FirmwareClient(payload=bytearray(b"\xff"))

        with self.assertLogs("avea.avea", level="WARNING") as logs:
            self.assertEqual(await bulb._read_manufacturer_name(), "")

        self.assertIn("Could not decode manufacturer name", "\n".join(logs.output))

    def test_smooth_transition_masks_expected_connection_error(self):
        bulb = Bulb("00:11:22:33:44:55")
        bulb.get_color = Mock(side_effect=BleakError("not connected"))

        with self.assertLogs("avea.avea", level="WARNING") as logs:
            bulb.set_smooth_transition(1, 2, 3)

        self.assertIn("Could not read current color", "\n".join(logs.output))

    def test_smooth_transition_propagates_unexpected_error(self):
        bulb = Bulb("00:11:22:33:44:55")
        bulb.get_color = Mock(side_effect=RuntimeError("bug"))

        with self.assertRaises(RuntimeError):
            bulb.set_smooth_transition(1, 2, 3)
