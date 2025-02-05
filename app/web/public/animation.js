const logo = document.querySelector(".box");
const button = document.querySelector(".runButton");

/*
  等价于以下 CSS @keyframes

  @keyframes colorChange {
    0% {
      background-color: grey;
    }
    100% {
      background-color: lime;
    }
  }
*/
const colorChangeFrames = { backgroundColor: ["grey", "lime"] };

function playAnimation() {
  logo.animate(colorChangeFrames, 4000);
}
button.addEventListener("click", playAnimation);
