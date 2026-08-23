import {
  applyVoice,
  describeError,
  getCurrentVoice,
  getStatus,
  getVisionSettings,
  listVoices,
  saveBackendConfig,
  saveVisionSettings,
  testFaceDetection,
  untilReady,
} from "../api.js";
import { h } from "../ui.js";

const HF_CONNECTION_MODES = Object.freeze({
  DEPLOYED: "deployed",
  LOCAL: "local",
});

const DEFAULT_HF_HOST = "localhost";
const DEFAULT_HF_PORT = 8765;

const HF_MODE_HINTS = Object.freeze({
  [HF_CONNECTION_MODES.DEPLOYED]: "Uses the hosted Hugging Face backend. No API key required.",
  [HF_CONNECTION_MODES.LOCAL]: "Connects directly to the host and port below.",
});

export async function mountSettingsView({ outlet, signal }) {
  const connectionSection = buildConnectionSection({
    onSaved: () =>
      Promise.all([
        refreshStatus({ statusSection, connectionSection, signal }),
        refreshVoices({ voiceSection, signal }),
        refreshVision({ visionSection, signal }),
      ]),
  });
  const visionSection = buildVisionSection();
  const voiceSection = buildVoiceSection();
  const statusSection = buildStatusSection();

  const view = h(
    "section",
    { class: "view view--settings" },
    h(
      "header",
      { class: "view-header" },
      h("h1", { class: "view-title" }, "Settings"),
      h("p", { class: "view-subtitle" }, "Connection, camera & vision, voice, and runtime state.")
    ),
    connectionSection.element,
    visionSection.element,
    voiceSection.element,
    statusSection.element
  );
  outlet.replaceChildren(view);

  await Promise.all([
    refreshStatus({ statusSection, connectionSection, signal }),
    refreshVoices({ voiceSection, signal }),
    refreshVision({ visionSection, signal }),
  ]);
}

function buildConnectionSection({ onSaved } = {}) {
  const hfModeSelect = h(
    "select",
    { class: "settings-select", name: "hf_mode" },
    h("option", { value: HF_CONNECTION_MODES.DEPLOYED }, "Hosted"),
    h("option", { value: HF_CONNECTION_MODES.LOCAL }, "Local")
  );
  const hfHostInput = h("input", {
    type: "text",
    name: "hf_host",
    autocomplete: "off",
    placeholder: DEFAULT_HF_HOST,
    value: DEFAULT_HF_HOST,
    class: "settings-input",
  });
  const hfPortInput = h("input", {
    type: "number",
    name: "hf_port",
    min: "1",
    max: "65535",
    step: "1",
    inputmode: "numeric",
    value: String(DEFAULT_HF_PORT),
    class: "settings-input",
  });
  const hfLocalFields = h(
    "div",
    { class: "settings-field-row", "data-role": "hf-local-fields" },
    h(
      "label",
      { class: "settings-field" },
      h("span", { class: "settings-label" }, "Host/IP"),
      hfHostInput
    ),
    h(
      "label",
      { class: "settings-field" },
      h("span", { class: "settings-label" }, "Port"),
      hfPortInput
    )
  );
  const hint = h("p", { class: "settings-hint" }, "");
  const status = h("p", { class: "settings-status", role: "status", "aria-live": "polite" });
  const submitButton = h("button", { type: "submit", class: "btn btn--primary" }, "Save connection");

  const form = h(
    "form",
    { class: "settings-form" },
    h(
      "label",
      { class: "settings-field" },
      h("span", { class: "settings-label" }, "Hugging Face connection"),
      hfModeSelect
    ),
    hfLocalFields,
    hint,
    h("div", { class: "settings-actions" }, submitButton),
    status
  );

  const element = h(
    "section",
    { class: "settings-section" },
    h("h2", { class: "settings-section-title" }, "Connection"),
    form
  );

  function syncLocalFields() {
    const isLocal = hfModeSelect.value === HF_CONNECTION_MODES.LOCAL;
    hfLocalFields.style.display = isLocal ? "" : "none";
    hfHostInput.disabled = !isLocal;
    hfPortInput.disabled = !isLocal;
    hfHostInput.required = isLocal;
    hfPortInput.required = isLocal;
    hint.textContent = HF_MODE_HINTS[hfModeSelect.value] || "";
  }

  hfModeSelect.addEventListener("change", syncLocalFields);

  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    if (submitButton.disabled) return;
    submitButton.disabled = true;
    hfModeSelect.disabled = true;
    hfHostInput.disabled = true;
    hfPortInput.disabled = true;
    form.setAttribute("aria-busy", "true");
    status.classList.remove("is-error");
    status.textContent = "Saving…";
    try {
      const payload = { hf_mode: hfModeSelect.value };
      if (hfModeSelect.value === HF_CONNECTION_MODES.LOCAL) {
        payload.hf_host = hfHostInput.value.trim();
        if (hfPortInput.value) {
          payload.hf_port = Number.parseInt(hfPortInput.value, 10);
        }
      }
      const result = await saveBackendConfig(payload);
      status.textContent =
        result?.message || (result?.requires_restart ? "Saved. Restart the app to apply." : "Saved.");
      await onSaved?.();
    } catch (error) {
      status.textContent = `Failed to save: ${describeError(error)}`;
      status.classList.add("is-error");
    } finally {
      submitButton.disabled = false;
      hfModeSelect.disabled = false;
      syncLocalFields();
      form.removeAttribute("aria-busy");
    }
  });

  syncLocalFields();

  return {
    element,
    syncFromStatus(payload) {
      if (Object.values(HF_CONNECTION_MODES).includes(payload?.hf_connection_mode)) {
        hfModeSelect.value = payload.hf_connection_mode;
      }
      if (payload?.hf_direct_host) {
        hfHostInput.value = payload.hf_direct_host;
      }
      if (payload?.hf_direct_port != null) {
        hfPortInput.value = String(payload.hf_direct_port);
      }
      syncLocalFields();
    },
  };
}

function buildVisionSection() {
  const cameraSelect = h("select", { class: "settings-select", name: "active_camera" });
  const faceEnabledInput = h("input", { type: "checkbox", class: "settings-checkbox", name: "face_detection_enabled", checked: true });
  const autoGazeInput = h("input", { type: "checkbox", class: "settings-checkbox", name: "auto_gaze_enabled", checked: true });
  const yoloEnabledInput = h("input", { type: "checkbox", class: "settings-checkbox", name: "yolo_detection_enabled", checked: true });

  const personNameInput = h("input", {
    type: "text",
    class: "settings-input",
    name: "registered_person_name",
    placeholder: "예: 앤디, 주인님, 팀장님",
    value: "사용자",
  });
  const personDescInput = h("input", {
    type: "text",
    class: "settings-input",
    name: "registered_person_desc",
    placeholder: "예: 검은 안경을 쓴 개발자, Reachy Mini 사용자",
    value: "주인님 / 사용자",
  });

  const previewImg = h("img", {
    class: "settings-camera-preview-img",
    src: "/api/camera/stream",
    alt: "Camera Live Preview",
  });
  previewImg.addEventListener("error", () => {
    setTimeout(() => {
      previewImg.src = `/api/camera/stream?t=${Date.now()}`;
    }, 2000);
  });

  const previewCard = h(
    "div",
    { class: "settings-camera-preview-card" },
    h(
      "div",
      { class: "settings-camera-preview-header" },
      h("span", { class: "settings-camera-live-dot" }),
      h("span", { class: "settings-camera-preview-label" }, "실시간 카메라 미리보기 (LIVE PREVIEW)")
    ),
    h("div", { class: "settings-camera-preview-frame" }, previewImg)
  );

  cameraSelect.addEventListener("change", async () => {
    try {
      await fetch(`/api/camera/select?device=${encodeURIComponent(cameraSelect.value)}`, { method: "POST" });
      previewImg.src = `/api/camera/stream?t=${Date.now()}`;
    } catch (err) {
      console.warn("Failed switching camera device in preview", err);
    }
  });

  const confSlider = h("input", {
    type: "range",
    class: "settings-range",
    min: "0.2",
    max: "0.9",
    step: "0.05",
    value: "0.5",
    name: "min_face_confidence",
  });
  const confValue = h("span", { class: "settings-range-val" }, "50%");

  confSlider.addEventListener("input", () => {
    confValue.textContent = `${Math.round(Number.parseFloat(confSlider.value) * 100)}%`;
  });

  const testBtn = h("button", { type: "button", class: "btn btn--outline" }, "🎯 얼굴 인식 테스트");
  const testResult = h("div", { class: "settings-vision-test-card" }, "얼굴 인식 테스트 버튼을 눌러 카메라 및 안면 인식을 테스트하세요.");

  testBtn.addEventListener("click", async () => {
    testBtn.disabled = true;
    testResult.className = "settings-vision-test-card is-loading";
    testResult.textContent = "얼굴을 감지하는 중…";
    try {
      const res = await testFaceDetection();
      if (res.detected) {
        testResult.className = "settings-vision-test-card is-success";
        testResult.replaceChildren(
          h("div", { class: "settings-vision-test-title" }, `✅ ${res.message}`),
          h("div", { class: "settings-vision-test-coords" }, `3D 위치: X(거리): ${res.coordinates_3d?.x}m, Y(좌우): ${res.coordinates_3d?.y}m, Z(높이): ${res.coordinates_3d?.z}m`)
        );
      } else {
        testResult.className = "settings-vision-test-card is-warn";
        testResult.textContent = `⚠️ ${res.message || "얼굴을 감지하지 못했습니다."}`;
      }
    } catch (e) {
      testResult.className = "settings-vision-test-card is-error";
      testResult.textContent = `❌ 테스트 실패: ${e?.message || e}`;
    } finally {
      testBtn.disabled = false;
    }
  });

  const personIdentitySection = h(
    "div",
    { class: "settings-person-identity-card" },
    h("h3", { class: "settings-subsection-title" }, "👤 인식 대상(사용자) 정의"),
    h(
      "div",
      { class: "settings-field-row" },
      h(
        "label",
        { class: "settings-field" },
        h("span", { class: "settings-label" }, "사용자 이름 / 호칭"),
        personNameInput,
        h("p", { class: "settings-hint" }, "얼굴 감지 시 로봇이 부를 이름입니다.")
      ),
      h(
        "label",
        { class: "settings-field" },
        h("span", { class: "settings-label" }, "사용자 특징 / 역할"),
        personDescInput,
        h("p", { class: "settings-hint" }, "로봇에게 전달될 사용자의 외형적 특징이나 설명입니다.")
      )
    )
  );

  const saveBtn = h("button", { type: "submit", class: "btn btn--primary" }, "비전 설정 저장");
  const status = h("p", { class: "settings-status", role: "status", "aria-live": "polite" });

  const form = h(
    "form",
    { class: "settings-form" },
    h(
      "label",
      { class: "settings-field" },
      h("span", { class: "settings-label" }, "입력 카메라 장치"),
      cameraSelect
    ),
    previewCard,
    personIdentitySection,
    h(
      "div",
      { class: "settings-vision-grid" },
      h(
        "label",
        { class: "settings-toggle-row" },
        faceEnabledInput,
        h(
          "div",
          { class: "settings-toggle-text" },
          h("strong", {}, "3D 안면 인식 (Face Detection)"),
          h("span", { class: "settings-hint" }, "카메라 영상에서 사용자 얼굴의 3D 공간 위치를 실시간 감지합니다.")
        )
      ),
      h(
        "label",
        { class: "settings-toggle-row" },
        autoGazeInput,
        h(
          "div",
          { class: "settings-toggle-text" },
          h("strong", {}, "자동 시선 맞춤 (Look-at Gaze)"),
          h("span", { class: "settings-hint" }, "얼굴 인식 시 로봇의 머리를 사용자 얼굴 방향으로 부드럽게 정렬합니다.")
        )
      ),
      h(
        "label",
        { class: "settings-toggle-row" },
        yoloEnabledInput,
        h(
          "div",
          { class: "settings-toggle-text" },
          h("strong", {}, "YOLOv8 사물 인식 (Object Detection)"),
          h("span", { class: "settings-hint" }, "노트북, 스마트폰, 컵 등 책상 위 사물을 실시간으로 식별합니다.")
        )
      )
    ),
    h(
      "label",
      { class: "settings-field" },
      h(
        "div",
        { class: "settings-field-head" },
        h("span", { class: "settings-label" }, "얼굴 인식 신뢰도 감도"),
        confValue
      ),
      confSlider
    ),
    h(
      "div",
      { class: "settings-test-area" },
      h("div", { class: "settings-actions" }, testBtn),
      testResult
    ),
    h("div", { class: "settings-actions" }, saveBtn),
    status
  );

  const element = h(
    "section",
    { class: "settings-section" },
    h("h2", { class: "settings-section-title" }, "Camera & Face Recognition"),
    form
  );

  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    if (saveBtn.disabled) return;
    saveBtn.disabled = true;
    status.classList.remove("is-error");
    status.textContent = "설정을 저장하는 중…";
    try {
      await saveVisionSettings({
        active_camera: cameraSelect.value,
        face_detection_enabled: faceEnabledInput.checked,
        auto_gaze_enabled: autoGazeInput.checked,
        yolo_detection_enabled: yoloEnabledInput.checked,
        registered_person_name: personNameInput.value.trim(),
        registered_person_desc: personDescInput.value.trim(),
        min_face_confidence: Number.parseFloat(confSlider.value),
      });
      status.textContent = "비전 및 얼굴 인식 설정이 저장되었습니다.";
    } catch (err) {
      status.textContent = `저장 실패: ${err?.message || err}`;
      status.classList.add("is-error");
    } finally {
      saveBtn.disabled = false;
    }
  });

  return {
    element,
    syncSettings(data) {
      if (!data) return;
      if (data.available_cameras) {
        cameraSelect.replaceChildren(
          ...data.available_cameras.map((c) =>
            h("option", { value: c.id, selected: c.id === data.active_camera }, c.name)
          )
        );
      }
      if (data.registered_person_name !== undefined) personNameInput.value = data.registered_person_name;
      if (data.registered_person_desc !== undefined) personDescInput.value = data.registered_person_desc;
      if (data.face_detection_enabled !== undefined) faceEnabledInput.checked = Boolean(data.face_detection_enabled);
      if (data.auto_gaze_enabled !== undefined) autoGazeInput.checked = Boolean(data.auto_gaze_enabled);
      if (data.yolo_detection_enabled !== undefined) yoloEnabledInput.checked = Boolean(data.yolo_detection_enabled);
      if (data.min_face_confidence !== undefined) {
        confSlider.value = String(data.min_face_confidence);
        confValue.textContent = `${Math.round(data.min_face_confidence * 100)}%`;
      }
    },
  };
}

function buildVoiceSection() {
  const select = h(
    "select",
    { class: "settings-select", name: "voice", disabled: "disabled" },
    h("option", { value: "" }, "Loading voices…")
  );
  const status = h("p", { class: "settings-status", role: "status", "aria-live": "polite" });
  const submitButton = h(
    "button",
    { type: "submit", class: "btn btn--primary", disabled: "disabled" },
    "Apply voice"
  );
  const form = h(
    "form",
    { class: "settings-form" },
    h("label", { class: "settings-field" }, h("span", { class: "settings-label" }, "Voice"), select),
    h("div", { class: "settings-actions" }, submitButton),
    status
  );

  const element = h(
    "section",
    { class: "settings-section" },
    h("h2", { class: "settings-section-title" }, "Voice"),
    form
  );

  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    if (submitButton.disabled || !select.value) return;
    submitButton.disabled = true;
    select.disabled = true;
    form.setAttribute("aria-busy", "true");
    status.classList.remove("is-error");
    status.textContent = "Applying…";
    try {
      const result = await applyVoice(select.value);
      status.textContent = result?.status || "Voice applied.";
    } catch (error) {
      status.textContent = `Failed to apply: ${describeError(error)}`;
      status.classList.add("is-error");
    } finally {
      submitButton.disabled = !select.value;
      select.disabled = !select.value;
      form.removeAttribute("aria-busy");
    }
  });

  return {
    element,
    setOptions(voices, current) {
      select.replaceChildren();
      if (!voices.length) {
        select.appendChild(h("option", { value: "" }, "No voices available"));
        select.disabled = true;
        submitButton.disabled = true;
        status.textContent = "Voices are unavailable right now.";
        return;
      }
      for (const v of voices) {
        const opt = h("option", { value: v }, v);
        if (v === current) opt.selected = true;
        select.appendChild(opt);
      }
      select.disabled = false;
      submitButton.disabled = false;
      status.textContent = "";
    },
  };
}

function buildStatusSection() {
  const list = h(
    "dl",
    { class: "settings-status-grid" },
    statusRow("Backend", "Loading…")
  );
  const element = h(
    "section",
    { class: "settings-section" },
    h("h2", { class: "settings-section-title" }, "Current state"),
    list
  );

  return {
    element,
    render(payload) {
      list.replaceChildren();
      list.appendChild(statusRow("HF connection", formatHfMode(payload.hf_connection_mode)));
      if (payload.hf_connection_mode === HF_CONNECTION_MODES.LOCAL) {
        list.appendChild(statusRow("HF target", formatHfTarget(payload)));
      }
      list.appendChild(
        statusRow(
          "Configuration",
          payload.has_hf_connection ? "Ready" : "Missing",
          payload.has_hf_connection ? "ok" : "warn"
        )
      );
      const backendState = payload.backend_connected
        ? "connected"
        : payload.backend_connection_state || "not_started";
      const backendLabels = {
        connected: "Connected",
        connecting: "Connecting…",
        disconnected: "Disconnected",
        not_started: "Not started",
        restart_required: "Restart required",
        waiting_for_config: "Waiting for configuration",
      };
      list.appendChild(
        statusRow(
          "Backend",
          backendLabels[backendState] || "Unavailable",
          backendState === "connected" ? "ok" : backendState === "not_started" ? undefined : "warn"
        )
      );
      if (payload.backend_error) {
        list.appendChild(statusRow("Backend error", payload.backend_error, "warn"));
      }
      if (payload.requires_restart) {
        list.appendChild(statusRow("Restart", "Required to apply changes", "warn"));
      }
    },
    renderUnavailable(error) {
      list.replaceChildren(statusRow("Backend", `Unavailable: ${describeError(error)}`, "warn"));
    },
  };
}

function statusRow(label, value, tone) {
  return h(
    "div",
    { class: ["settings-status-row", tone && `is-${tone}`] },
    h("dt", { class: "settings-status-label" }, label),
    h("dd", { class: "settings-status-value" }, value)
  );
}

function formatHfMode(mode) {
  if (mode === HF_CONNECTION_MODES.LOCAL) return "Local";
  if (mode === HF_CONNECTION_MODES.DEPLOYED) return "Hosted";
  return "-";
}

function formatHfTarget(payload) {
  const host = payload?.hf_direct_host;
  const port = payload?.hf_direct_port;
  if (!host) return "-";
  return `${host}:${port || DEFAULT_HF_PORT}`;
}

async function refreshStatus({ statusSection, connectionSection, signal }) {
  try {
    const payload = await untilReady(getStatus, signal);
    if (signal.aborted) return;
    statusSection.render(payload);
    connectionSection.syncFromStatus(payload);
  } catch (error) {
    if (signal.aborted) return;
    statusSection.renderUnavailable(error);
  }
}

async function refreshVoices({ voiceSection, signal }) {
  let voices = [];
  let current = "";
  try {
    voices = await untilReady(listVoices, signal);
  } catch {
    voices = [];
  }
  if (signal.aborted) return;
  try {
    const data = await getCurrentVoice();
    current = data?.voice || "";
  } catch {
    current = "";
  }
  if (signal.aborted) return;
  voiceSection.setOptions(voices, current);
}

async function refreshVision({ visionSection, signal }) {
  try {
    const data = await getVisionSettings();
    if (signal.aborted) return;
    visionSection.syncSettings(data);
  } catch (err) {
    console.debug("Failed refreshing vision settings", err);
  }
}
