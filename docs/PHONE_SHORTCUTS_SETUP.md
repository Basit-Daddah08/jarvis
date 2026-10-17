# Phone Capture Setup: iOS Shortcuts & Android HTTP Shortcuts

Save Instagram Reels, TikToks, and YouTube Shorts straight into your private ELION vault with zero interruption. Tapping **Share &rarr; Save to ELION** on your phone queues the video in <10ms without switching apps. Your laptop daemon downloads audio-only in the background, transcribes it locally via Whisper, extracts tools and steps, and writes structured notes to `vault/notes/`.

---

## 1. Prerequisites

### A. Tailscale Connection
1. Ensure Tailscale is installed on both your **laptop** and your **phone** (connected to the same Tailscale tailnet).
2. Find your laptop's Tailscale IPv4 address:
   * **Terminal on laptop:** Run `tailscale ip -4` (it will be in the `100.x.y.z` range, e.g. `100.85.12.34`).
   * **Tailscale App:** Open the Tailscale app on your phone or laptop and tap your laptop device name to copy the IP.
3. Enable Tailscale interface access in ELION:
   * In `config.toml` under `[daemon]`, set:
     ```toml
     [daemon]
     allow_tailscale = true
     bind_address = "127.0.0.1"
     ```
   * Or open your laptop dashboard at `http://127.0.0.1:8080` and toggle **Allow Tailscale Interface** in settings.

### B. Your Long Random Security Token
All phone requests require your private `ELION_AUTH_TOKEN`:
* Stored securely in your laptop's `.env` file (`ELION_AUTH_TOKEN=...`).
* You can also view and copy it from your local laptop dashboard (`http://127.0.0.1:8080`) under the **Daemon & Sync** tab.

---

## 2. iOS Shortcut Setup (Step-by-Step)

### Step 1: Create the Shortcut
1. Open the built-in **Shortcuts** app on your iPhone.
2. Tap the **+** (plus) icon in the top right corner to create a new shortcut.
3. Tap the name at the top and rename it to: `Save to ELION`.

### Step 2: Configure Share Sheet Input
1. Tap the **(i)** (Details / Information) icon at the bottom of the screen.
2. Toggle **Show in Share Sheet** to **ON**.
3. Under **Receive**, tap **Any** and select:
   * **URLs**
   * **Text**
   * **Safari web pages**
4. Tap **Done**.

### Step 3: Add URL Extraction Action
1. Tap **Add Action**.
2. Search for `Get URLs from Input` and tap to add it.
   * *This ensures tracking text or messages shared along with the link are properly parsed to the raw link.*

### Step 4: Add HTTP Request Action
1. Search for and add the action: `Get Contents of URL`.
2. Tap on `URL` in the action box and enter:
   ```text
   http://<YOUR-TAILSCALE-IP>:8080/api/save
   ```
   *(Replace `<YOUR-TAILSCALE-IP>` with your laptop's Tailscale IP, e.g. `http://100.85.12.34:8080/api/save`)*
3. Tap the arrow **(&gt;)** or **Show More** to expand the advanced network options:
   * **Method:** Select `POST`.
   * **Headers:**
     * Tap **Add new header**.
     * Key: `X-Elion-Token`
     * Value: `<YOUR-ELION-AUTH-TOKEN>`
     * Tap **Add new header**.
     * Key: `Content-Type`
     * Value: `application/json`
   * **Request Body:** Select `JSON`.
     * Tap **Add new field** &rarr; select **Text**.
     * Key: `url`
     * Value: Tap the field and choose **URLs** (the output from Step 3).
     * Tap **Add new field** &rarr; select **Text**.
     * Key: `token`
     * Value: `<YOUR-ELION-AUTH-TOKEN>`

### Step 5: Add Instant Confirmation Feedback (Optional)
1. Search for and add the action: `Show Notification`.
2. Set text to: `Saved to ELION` (Body: `Video queued for background Whisper transcription`).
3. Tap **Done** in the top right corner to save the shortcut.

### How to Use on iPhone:
* Open **Instagram**, **TikTok**, or **YouTube**.
* On any reel or short, tap **Share** &rarr; scroll down the share sheet and tap **Save to ELION**.
* The shortcut fires in ~5ms and dismisses automatically without opening any browser or interrupting your scroll.

---

## 3. Android HTTP Shortcuts Setup (Step-by-Step)

### Step 1: Install HTTP Shortcuts
1. Install **HTTP Shortcuts** from Google Play Store or F-Droid (free & open source).

### Step 2: Create a New Shortcut
1. Open HTTP Shortcuts.
2. Tap the floating **+** button &rarr; select **Regular HTTP Request**.
3. Set **Shortcut Name**: `Save to ELION`.

### Step 3: Configure URL & Method
1. In the **Basic Request Settings** section:
   * **Method:** `POST`
   * **URL:** `http://<YOUR-TAILSCALE-IP>:8080/api/save`
     *(Replace `<YOUR-TAILSCALE-IP>` with your laptop's Tailscale IP, e.g. `http://100.85.12.34:8080/api/save`)*

### Step 4: Configure Headers
1. Tap **Request Headers**:
   * Add Header 1:
     * Key: `Content-Type`
     * Value: `application/json`
   * Add Header 2:
     * Key: `X-Elion-Token`
     * Value: `<YOUR-ELION-AUTH-TOKEN>`

### Step 5: Configure Request Body & Variables
1. Tap **Request Body / Parameters**:
   * **Body Type:** `Custom Text / JSON`
   * Enter the JSON payload:
     ```json
     {
       "url": "{share_url}",
       "token": "<YOUR-ELION-AUTH-TOKEN>"
     }
     ```
2. Tap **Variables** (or create variable `{share_url}`):
   * Type: `Share / Intent Data` or `Text`.
   * Under shortcut properties, enable **Show in Share Menu / Share Target** so Android registers the shortcut in your system share dialog.

### Step 6: Configure Silent Feedback
1. Tap **Response Handling**:
   * **Show Response:** Select `Show Toast` (or `None` for silent background execution).
   * **Success Message:** `Saved to ELION`.
2. Tap the checkmark icon in the top right to save.

### How to Use on Android:
* Open **Instagram**, **TikTok**, or **YouTube**.
* Tap **Share** &rarr; select **HTTP Shortcuts: Save to ELION**.
* A brief toast confirms `Saved to ELION` while the background daemon handles transcription on your laptop.

---

## 4. Alternative: Laptop Clipboard Auto-Capture

If you don't want to use shortcuts:
1. Tap **Copy Link** on your phone.
2. If you use **Windows Phone Link** or **KDE Connect** (shared clipboard), the link automatically syncs to your laptop.
3. ELION's background clipboard watcher detects the link, validates that it is from Instagram, TikTok, or YouTube, de-duplicates it, and immediately queues it.
4. **Toggle Clipboard Watcher:**
   * In your laptop dashboard (`http://127.0.0.1:8080`), click the **Clipboard Auto-Capture** button to toggle between `ACTIVE` and `PAUSED`.
   * Or run via API: `curl -X POST http://127.0.0.1:8080/api/daemon/toggle_clipboard`

---

## 5. Security & Verification Summary

* **Network Isolation:** Only `localhost` (`127.0.0.1`) and Tailscale CGNAT IPs (`100.64.0.0/10`) can reach this endpoint.
* **Token Guard:** Every request without a matching `ELION_AUTH_TOKEN` is rejected (`401 Unauthorized`).
* **Platform Filter:** Only Instagram, TikTok, and YouTube URLs are accepted (`400 Bad Request` for arbitrary links).
* **De-duplication:** Re-sharing an already processed or queued link returns an instant 200 without redundant downloads.
* **Rate Limiting:** Protects against runaway shortcut loops (up to 30 requests/minute).
