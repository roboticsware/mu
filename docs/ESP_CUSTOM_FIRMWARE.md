# Custom ESP Firmware Hosting Guide (TFLite-Micro / Edge Impulse / ulab)

Mu's ESP flashers (**ESP Online Flasher** and **ESP Firmware flasher**) support flashing custom MicroPython builds (such as ESP32-S3 firmware with `tflite`, `microlite`, `edge_impulse`, or `ulab` C modules) from both online and offline sources.

## 1. Pre-configuring Default Online Sources

To make your custom firmware releases appear automatically in the **ESP Online Flasher** dropdown when users click **Fetch Versions**, use either option below:

### Option A: Add a Manifest URL in Code (`CUSTOM_MANIFEST_URLS`)

Edit `mu/interface/esp_flasher/fetcher.py` and add your manifest or GitHub Releases URL to `CUSTOM_MANIFEST_URLS`:

```python
CUSTOM_MANIFEST_URLS: list[str] = [
    "https://github.com/your-org/your-tflite-micropython-repo",
    # or a JSON manifest URL:
    # "https://example.com/esp-custom-firmwares.json",
]
```

### Option B: Set the Environment Variable (`MU_ESP_CUSTOM_MANIFEST_URL`)

Set `MU_ESP_CUSTOM_MANIFEST_URL` before launching Mu:

```bash
export MU_ESP_CUSTOM_MANIFEST_URL="https://example.com/esp-custom-firmwares.json"
python run.py
```

## 2. JSON Manifest Format

A custom JSON manifest can be either a JSON array or an object with a `"firmwares"` array:

```json
{
  "firmwares": [
    {
      "label": "ESP32-S3 TFLite-Micro + Camera",
      "family": "esp32s3",
      "version": "1.27.0-tflite",
      "url": "https://github.com/your-org/repo/releases/download/v1.0.0/mpy-tflite-esp32s3.zip",
      "flash_offset": "0x0"
    }
  ]
}
```

- `label` (or `name`): Display name in the **Board** dropdown.
- `family`: Target chip for `esptool` (`esp32s3`, `esp32`, `esp32s2`, `esp32c3`, `esp32c6`, `esp8266`). If omitted, Mu infers it from the label/URL.
- `version`: Version tag shown in the **Version** dropdown.
- `url`: Direct download URL to a `.bin` or `.zip` firmware package.
- `flash_offset` *(optional)*: Explicit hex offset (for single `.bin` files; ignored for multi-part `.zip` archives).

## 3. Ad-hoc Custom URLs in the UI

Users can also paste any of the following directly into **Custom URL** in **ESP Online Flasher** and click **Load**:
- A GitHub repository or Releases URL (e.g. `https://github.com/org/repo`)
- A JSON manifest URL (`*.json`)
- A direct `.bin` or `.zip` download URL

## 4. Supported `.bin` & `.zip` Package Formats

Both the online and offline flashers automatically resolve single `.bin` files and multi-part `.zip` archives in the following order:
1. `flasher_args.json` (standard ESP-IDF / Edge Impulse `flash_files` mapping)
2. `flash_args` text file (`0xADDR file.bin` pairs)
3. Heuristic multi-part `.bin` matching (`*bootloader*` -> `0x0`/`0x1000`, `*partition*` -> `0x8000`, `*ota_data*` -> `0xd000`, app `.bin` -> `0x10000`)
4. Single merged `.bin` inside `.zip` (written at the selected **Offset** or chip default: `0x0` for ESP32-S3/C3/C6/ESP8266, `0x1000` for ESP32/ESP32-S2).
