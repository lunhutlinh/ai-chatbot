async function callChatApi(message) {
  const res = await fetch("/chude6/chat", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ message }),
  });

  if (!res.ok) {
    const bodyText = await res.text().catch(() => "");
    throw new Error(`HTTP ${res.status} ${bodyText}`.trim());
  }

  return await res.json();
}

function appendMessage(role, text) {
  const chatBox = document.getElementById("chatBox");
  const msg = document.createElement("div");
  msg.className = `message ${role}`;
  msg.innerText = text;
  chatBox.appendChild(msg);
  chatBox.scrollTop = chatBox.scrollHeight;
  return msg;
}

function showChatViewIfNeeded() {
  const welcomeScreen = document.getElementById("welcomeScreen");
  const chatContainer = document.getElementById("chatContainer");
  if (welcomeScreen?.style.display !== "none") {
    welcomeScreen.style.display = "none";
    chatContainer.style.display = "flex";
  }
}

function isWelcomeVisible() {
  const welcomeScreen = document.getElementById("welcomeScreen");
  return welcomeScreen && welcomeScreen.style.display !== "none";
}

function getActiveInput() {
  const userInput = document.getElementById("userInput");
  const userInput2 = document.getElementById("userInput2");
  if (!isWelcomeVisible() && userInput2) return userInput2;
  return userInput;
}

async function sendMessage() {
  const input = getActiveInput();
  if (!input) return;

  const text = (input.value || "").trim();
  if (text === "") return;

  const onWelcome = isWelcomeVisible();

  if (onWelcome) {
    const welcomeTitle = document.querySelector(".welcome-title");
    const inputWrapper = document.querySelector(".input-wrapper");
    welcomeTitle?.classList.add("move-up");
    inputWrapper?.classList.add("expand-down");

    setTimeout(() => {
      showChatViewIfNeeded();
    }, 800);

    setTimeout(() => {
      appendMessage("user", text);

      input.value = "";
      const userInput2 = document.getElementById("userInput2");
      if (userInput2) {
        userInput2.value = "";
        userInput2.focus();
      }
    }, 800);

    setTimeout(async () => {
      const botMsg = appendMessage("bot", "Đang xử lý câu hỏi của bạn...");
      try {
        const data = await callChatApi(text);
        botMsg.innerText =
          data?.reply || data?.rag_reply || "(Không có phản hồi)";
      } catch (err) {
        botMsg.innerText =
          "Mình gặp lỗi khi gọi API. Bạn thử chạy API rồi tải lại trang nhé.";
        console.error(err);
      }
    }, 1000);

    return;
  }

  appendMessage("user", text);
  input.value = "";
  input.focus();

  const botMsg = appendMessage("bot", "Đang xử lý câu hỏi của bạn...");
  try {
    const data = await callChatApi(text);
    botMsg.innerText = data?.reply || data?.rag_reply || "(Không có phản hồi)";
  } catch (err) {
    botMsg.innerText =
      "Mình gặp lỗi khi gọi API. Bạn thử chạy API rồi tải lại trang nhé.";
    console.error(err);
  }
}

// Trigger animation when clicking on input
document.getElementById("userInput")?.addEventListener("focus", function () {
  const welcomeTitle = document.querySelector(".welcome-title");
  const inputWrapper = document.querySelector(".input-wrapper");

  if (welcomeTitle && !welcomeTitle.classList.contains("move-up")) {
    welcomeTitle.classList.add("move-up");
    inputWrapper?.classList.add("expand-down");

    setTimeout(() => {
      showChatViewIfNeeded();
      document.getElementById("userInput2")?.focus();
    }, 800);
  }
});

// Enter để gửi
document
  .getElementById("userInput")
  ?.addEventListener("keypress", function (e) {
    if (e.key === "Enter") sendMessage();
  });

document
  .getElementById("userInput2")
  ?.addEventListener("keypress", function (e) {
    if (e.key === "Enter") sendMessage();
  });
