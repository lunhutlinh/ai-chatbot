function sendMessage() {
  let input = document.getElementById("userInput");
  let text = input.value.trim();

  if (text === "") return;

  // Trigger title animation
  let welcomeTitle = document.querySelector(".welcome-title");
  let inputWrapper = document.querySelector(".input-wrapper");
  welcomeTitle.classList.add("move-up");
  inputWrapper.classList.add("expand-down");

  // Hide welcome screen and show chat after animation completes
  setTimeout(() => {
    document.getElementById("welcomeScreen").style.display = "none";
    document.getElementById("chatContainer").style.display = "flex";
  }, 800);

  let chatBox = document.getElementById("chatBox");
  let userInput2 = document.getElementById("userInput2");

  // User message
  setTimeout(() => {
    let userMsg = document.createElement("div");
    userMsg.className = "message user";
    userMsg.innerText = text;
    chatBox.appendChild(userMsg);

    input.value = "";
    userInput2.value = "";
    userInput2.focus();
  }, 800);

  // Fake bot reply (demo)
  setTimeout(() => {
    let botMsg = document.createElement("div");
    botMsg.className = "message bot";
    botMsg.innerText = "Đang xử lý câu hỏi của bạn...";
    chatBox.appendChild(botMsg);

    chatBox.scrollTop = chatBox.scrollHeight;
  }, 1300);
}

// Trigger animation when clicking on input
document.getElementById("userInput").addEventListener("focus", function () {
  let welcomeTitle = document.querySelector(".welcome-title");
  let inputWrapper = document.querySelector(".input-wrapper");

  if (!welcomeTitle.classList.contains("move-up")) {
    welcomeTitle.classList.add("move-up");
    inputWrapper.classList.add("expand-down");

    setTimeout(() => {
      document.getElementById("welcomeScreen").style.display = "none";
      document.getElementById("chatContainer").style.display = "flex";
    }, 800);
  }
});

// Enter để gửi
document.getElementById("userInput").addEventListener("keypress", function (e) {
  if (e.key === "Enter") {
    sendMessage();
  }
});

document
  .getElementById("userInput2")
  ?.addEventListener("keypress", function (e) {
    if (e.key === "Enter") {
      let text = this.value.trim();
      if (text === "") return;

      let chatBox = document.getElementById("chatBox");

      // User message
      let userMsg = document.createElement("div");
      userMsg.className = "message user";
      userMsg.innerText = text;
      chatBox.appendChild(userMsg);

      this.value = "";

      // Fake bot reply
      setTimeout(() => {
        let botMsg = document.createElement("div");
        botMsg.className = "message bot";
        botMsg.innerText = "Đang xử lý câu hỏi của bạn...";
        chatBox.appendChild(botMsg);

        chatBox.scrollTop = chatBox.scrollHeight;
      }, 500);
    }
  });
