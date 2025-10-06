"""
Creator : k0rventen
License : MIT
Source  : https://github.com/k0rventen/avea
Version : 1.5.2
"""

import asyncio
import logging
import math
import threading
from contextlib import suppress
from typing import Awaitable, Callable, Optional, Sequence

from bleak import BleakClient, BleakScanner
from bleak.exc import BleakError
from bleak.backends.device import BLEDevice
from bleak_retry_connector import establish_connection

__all__ = [
    "Bulb",
    "discover_avea_bulbs",
    "compute_brightness",
    "compute_transition_table",
    "compute_color",
    "check_bounds",
]

FIRMWARE_REVISION_UUID = "00002a26-0000-1000-8000-00805f9b34fb"
AVEA_SERVICE_UUID = "f815e810-456c-6761-746f-4d756e696368"
CONTROL_CHARACTERISTIC_UUID = "f815e811-456c-6761-746f-4d756e696368"
MAX_TRANSITION_FPS = 5


_LOGGER = logging.getLogger(__name__)


class Bulb:
    """The class that represents an Avea bulb."""

    def __init__(self, address: str):
        self.addr = address
        self.name = "Unknown"
        self.fw_version = "Unknown"
        self.red = 0
        self.blue = 0
        self.green = 0
        self.brightness = 0
        self.white = 0

        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._loop_thread: Optional[threading.Thread] = None
        self._loop_ready: Optional[threading.Event] = None
        self._client: Optional[BleakClient] = None
        self._notification_event: Optional[asyncio.Event] = None
        self._expected_cmd: Optional[int] = None
        self._op_lock = threading.RLock()
        self._color_known = False
        self._device: Optional[BLEDevice] = None

    # ------------------------------------------------------------------
    # Event loop helpers
    # ------------------------------------------------------------------
    def _start_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        asyncio.set_event_loop(loop)
        if self._loop_ready:
            self._loop_ready.set()
        loop.run_forever()

    def _ensure_loop(self) -> None:
        if self._loop is not None:
            return
        loop = asyncio.new_event_loop()
        self._loop = loop
        self._loop_ready = threading.Event()
        self._loop_thread = threading.Thread(
            target=self._start_loop, args=(loop,), daemon=True
        )
        self._loop_thread.start()
        self._loop_ready.wait()

    def _submit(self, coro: Awaitable):
        self._ensure_loop()
        future = asyncio.run_coroutine_threadsafe(coro, self._loop)
        return future.result()

    def _shutdown_loop(self) -> None:
        loop = self._loop
        thread = self._loop_thread
        if loop is None:
            return
        loop.call_soon_threadsafe(loop.stop)
        if thread and thread.is_alive():
            thread.join(timeout=1)
        loop.close()
        self._loop = None
        self._loop_thread = None
        self._loop_ready = None

    def close(self) -> None:
        with self._op_lock:
            if self._loop is None:
                return
            with suppress(Exception):
                if self._client:
                    self._submit(self._disconnect())
            self._shutdown_loop()

    def __del__(self):
        with suppress(Exception):
            self.close()

    # ------------------------------------------------------------------
    # Connection handling
    # ------------------------------------------------------------------
    def _notification_handler(self, _: int, data: bytearray) -> None:
        payload = bytes(data)
        self.process_notification(payload)
        event = self._notification_event
        expected = self._expected_cmd
        if event is not None and (expected is None or (payload and payload[0] == expected)):
            event.set()

    async def _connect(self) -> bool:
        if self._client and self._client.is_connected:
            return True

        client: Optional[BleakClient] = None
        try:
            device: Optional[BLEDevice]
            if isinstance(self.addr, BLEDevice):
                device = self.addr
            elif self._device:
                device = self._device
            else:
                device = await BleakScanner.find_device_by_address(
                    self.addr, timeout=5.0
                )
            if device is None:
                raise BleakError(f"Device {self.addr} not found")
            self._device = device
            display_name = (
                device.name
                or (self.name if self.name != "Unknown" else self.addr)
            )
            client = await establish_connection(
                BleakClient,
                device,
                display_name,
                timeout=15.0,
                use_services_cache=False,
            )
            await client.start_notify(
                CONTROL_CHARACTERISTIC_UUID,
                self._notification_handler,
            )
        except Exception as exc:
            _LOGGER.warning("Could not connect to the Bulb %s: %s", self.addr, exc)
            with suppress(Exception):
                if client:
                    await client.disconnect()
            return False

        self._client = client
        return True

    async def _disconnect(self) -> None:
        client = self._client
        self._client = None
        if not client:
            return
        with suppress(Exception):
            await client.stop_notify(CONTROL_CHARACTERISTIC_UUID)
        with suppress(Exception):
            await client.disconnect()

    def subscribe_to_notification(self):
        """Notifications are handled directly by bleak during connect."""
        return True

    def connect(self) -> bool:
        with self._op_lock:
            return self._submit(self._connect())

    def disconnect(self) -> None:
        with self._op_lock:
            if not self._client:
                return
            self._submit(self._disconnect())

    def _is_connected(self) -> bool:
        return self._client is not None and self._client.is_connected

    # ------------------------------------------------------------------
    # Command helpers
    # ------------------------------------------------------------------
    async def _write_command(self, payload: bytes, *, with_response: bool = False) -> None:
        if not self._client or not self._client.is_connected:
            raise BleakError("Client is not connected")
        await self._client.write_gatt_char(
            CONTROL_CHARACTERISTIC_UUID,
            payload,
            response=with_response,
        )

    async def _request_notification(
        self,
        command: bytes,
        expected_cmd: Optional[int],
        delay: float = 0.0,
        timeout: float = 1.0,
    ) -> None:
        if not self._client or not self._client.is_connected:
            raise BleakError("Client is not connected")
        if delay:
            await asyncio.sleep(delay)
        event = asyncio.Event()
        self._notification_event = event
        self._expected_cmd = expected_cmd
        try:
            await self._client.write_gatt_char(CONTROL_CHARACTERISTIC_UUID, command, response=False)
            await asyncio.wait_for(event.wait(), timeout)
        except asyncio.TimeoutError:
            pass
        finally:
            self._notification_event = None
            self._expected_cmd = None

    async def _read_firmware_version(self) -> str:
        if not self._client:
            return ""
        try:
            payload = await self._client.read_gatt_char(FIRMWARE_REVISION_UUID)
        except (BleakError, AttributeError) as exc:
            print(exc, "get_fw_version")
            return ""
        if isinstance(payload, bytearray):
            payload = bytes(payload)
        try:
            return payload.decode("utf-8")
        except Exception:
            return ""

    async def _smooth_transition(
        self,
        red_table: Sequence[int],
        green_table: Sequence[int],
        blue_table: Sequence[int],
        interval: float,
    ) -> None:
        if not self._client or not self._client.is_connected:
            raise BleakError("Client is not connected")
        last_payload = None
        for index, (r, g, b) in enumerate(zip(red_table, green_table, blue_table), start=1):
            payload = compute_color(
                check_bounds(0),
                check_bounds(r),
                check_bounds(g),
                check_bounds(b),
            )
            try:
                await self._write_command(payload, with_response=False)
            except Exception:
                await self._disconnect()
                if not await self._connect():
                    break
                await self._write_command(payload, with_response=False)
            if interval:
                await asyncio.sleep(interval)
            last_payload = payload
        if last_payload is not None:
            await self._write_command(last_payload, with_response=True)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def get_fw_version(self) -> str:
        with self._op_lock:
            already_connected = self._is_connected()
            if not already_connected and not self.connect():
                self.fw_version = ""
                return ""
            value = self._submit(self._read_firmware_version())
            if not already_connected:
                self.disconnect()
        result = value if isinstance(value, str) else ""
        self.fw_version = result
        return result

    def set_brightness(self, brightness):
        with self._op_lock:
            payload = compute_brightness(check_bounds(brightness))
            already_connected = self._is_connected()
            if not already_connected and not self.connect():
                return
            self._submit(self._write_command(payload))
            if not already_connected:
                self.disconnect()
        self.brightness = check_bounds(brightness)

    def get_brightness(self):
        with self._op_lock:
            already_connected = self._is_connected()
            if not already_connected and not self.connect():
                return self.brightness
            self._submit(
                self._request_notification(b"\x57", expected_cmd=0x57, delay=0.5)
            )
            if not already_connected:
                self.disconnect()
            return self.brightness

    def set_color(self, white, red, green, blue):
        with self._op_lock:
            payload = compute_color(
                check_bounds(white),
                check_bounds(red),
                check_bounds(green),
                check_bounds(blue),
            )
            already_connected = self._is_connected()
            if not already_connected and not self.connect():
                return
            self._submit(self._write_command(payload))
            if not already_connected:
                self.disconnect()
        self.white = check_bounds(white)
        self.red = check_bounds(red)
        self.green = check_bounds(green)
        self.blue = check_bounds(blue)
        self._color_known = True

    def set_rgb(self, red, green, blue):
        with self._op_lock:
            self.set_color(0, red * 16, green * 16, blue * 16)

    def set_smooth_transition(self, target_red, target_green, target_blue, duration=2, fps=60):
        if self._color_known:
            init_r = self.red
            init_g = self.green
            init_b = self.blue
        else:
            try:
                init_w, init_r, init_g, init_b = self.get_color()
            except Exception:
                print("Could not connect to bulb")
                return

        with self._op_lock:
            clamped_fps = max(1, min(int(fps), MAX_TRANSITION_FPS))
            iterations = max(1, int(duration * clamped_fps))
            interval = 0 if clamped_fps <= 0 else 1 / clamped_fps
            target_red_12 = check_bounds(target_red * 16)
            target_green_12 = check_bounds(target_green * 16)
            target_blue_12 = check_bounds(target_blue * 16)
            red_table = compute_transition_table(init_r, target_red_12, iterations)
            green_table = compute_transition_table(init_g, target_green_12, iterations)
            blue_table = compute_transition_table(init_b, target_blue_12, iterations)
            already_connected = self._is_connected()
            if not already_connected and not self.connect():
                return
            self._submit(
                self._smooth_transition(red_table, green_table, blue_table, interval)
            )
            self.red = target_red_12
            self.green = target_green_12
            self.blue = target_blue_12
            self._color_known = True
            if not already_connected:
                self.disconnect()

    def get_color(self):
        with self._op_lock:
            already_connected = self._is_connected()
            if not already_connected and not self.connect():
                return self.white, self.red, self.green, self.blue
            self._submit(
                self._request_notification(b"\x35", expected_cmd=0x35, delay=0.5)
            )
            if not already_connected:
                self.disconnect()
            self._color_known = True
            return self.white, self.red, self.green, self.blue

    def get_rgb(self):
        with self._op_lock:
            already_connected = self._is_connected()
            if not already_connected and not self.connect():
                return int(self.red / 16), int(self.green / 16), int(self.blue / 16)
            self._submit(
                self._request_notification(b"\x35", expected_cmd=0x35, delay=0.5)
            )
            if not already_connected:
                self.disconnect()
            self._color_known = True
            return int(self.red / 16), int(self.green / 16), int(self.blue / 16)

    def get_name(self):
        with self._op_lock:
            already_connected = self._is_connected()
            if not already_connected and not self.connect():
                return self.name
            self._submit(
                self._request_notification(b"\x58", expected_cmd=0x58, delay=0.5)
            )
            if not already_connected:
                self.disconnect()
            return self.name

    def set_name(self, name: str):
        with self._op_lock:
            byte_name = name.encode("utf-8")
            command = b"\x58" + byte_name
            already_connected = self._is_connected()
            if not already_connected and not self.connect():
                return
            self._submit(self._write_command(command))
            if not already_connected:
                self.disconnect()

    def process_notification(self, data: bytes):
        if not data:
            return
        cmd = data[0]
        values = data[1:]

        if cmd == 0x57:
            self.brightness = int.from_bytes(values, "little")

        elif cmd == 0x35:
            hex_val = values.hex()
            self.red = int.from_bytes(bytes.fromhex(hex_val[-4:]), "little") ^ int(0x3000)
            self.green = int.from_bytes(bytes.fromhex(hex_val[-8:-4]), "little") ^ int(0x2000)
            self.blue = int.from_bytes(bytes.fromhex(hex_val[-12:-8]), "little") ^ int(0x1000)
            self.white = int.from_bytes(bytes.fromhex(hex_val[-16:-12]), "little")
            self._color_known = True

        elif cmd == 0x58:
            try:
                self.name = values.decode("utf-8")
            except Exception:
                self.name = "Unknown"


# ----------------------------------------------------------------------
# Discovery helpers
# ----------------------------------------------------------------------
async def _discover(timeout: float) -> list:
    devices = await BleakScanner.discover(timeout=timeout)
    bulbs = []
    for dev in devices:
        if _is_avea_device(dev):
            bulb = Bulb(dev.address)
            bulb._device = dev
            if getattr(dev, "name", None):
                bulb.name = dev.name
            bulbs.append(bulb)
    return bulbs


def _is_avea_device(device) -> bool:
    name_sources = [getattr(device, "name", None)]
    metadata = getattr(device, "metadata", {}) or {}
    name_sources.append(metadata.get("local_name"))

    for name in name_sources:
        if name and "Avea" in name:
            return True

    for value in metadata.get("manufacturer_data", {}).values():
        try:
            decoded = bytes(value).decode("utf-8", errors="ignore")
        except Exception:
            continue
        if "Avea" in decoded:
            return True

    for uuid in metadata.get("uuids", []) or []:
        if isinstance(uuid, str) and "Avea" in uuid:
            return True

    return False


def _run_async(factory: Callable[[], Awaitable]):
    try:
        return asyncio.run(factory())
    except RuntimeError:
        result = {}
        error = {}

        def runner():
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                result["value"] = loop.run_until_complete(factory())
            except Exception as exc:
                error["exc"] = exc
            finally:
                loop.close()

        thread = threading.Thread(target=runner)
        thread.start()
        thread.join()
        if "exc" in error:
            raise error["exc"]
        return result.get("value")


def discover_avea_bulbs(timeout: float = 4.0):
    return _run_async(lambda: _discover(timeout))


# ----------------------------------------------------------------------
# Utility functions
# ----------------------------------------------------------------------

def compute_brightness(brightness):
    """Return the payload for the specified brightness."""
    value = hex(int(brightness))[2:]
    value = value.zfill(4)
    value = value[2:] + value[:2]
    return bytes.fromhex("57" + value)


def compute_color(w=2000, r=0, g=0, b=0):
    """Return the payload for the specified colors."""
    color = "35"
    fading = "1101"
    unknown = "0a00"
    white = (int(w) | int(0x8000)).to_bytes(2, byteorder="little").hex()
    red = (int(r) | int(0x3000)).to_bytes(2, byteorder="little").hex()
    green = (int(g) | int(0x2000)).to_bytes(2, byteorder="little").hex()
    blue = (int(b) | int(0x1000)).to_bytes(2, byteorder="little").hex()

    return bytes.fromhex(color + fading + unknown + white + red + green + blue)


def compute_transition_table(init, target, iterations):
    """Compute a list of values for a smooth transition between 2 numbers."""
    iterations = max(1, int(iterations))
    if iterations == 1:
        return [target]
    delta = target - init
    values = []
    for n in range(1, iterations + 1):
        frac = n / iterations
        eased = (1 - math.cos(math.pi * frac)) / 2
        values.append(round(init + delta * eased))
    return values


def check_bounds(value):
    """Check if the given value is out-of-bounds (0 to 4095)."""
    try:
        ivalue = int(value)
    except ValueError:
        print("Value was not a number, returned default value of 0")
        return 0

    if ivalue > 4095:
        return 4095
    if ivalue < 0:
        return 0
    return ivalue
