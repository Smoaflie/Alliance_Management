const docStyle = document.documentElement.style
const aElem = document.querySelector('button-3d')
const boundingClientRect = aElem.getBoundingClientRect()

aElem.addEventListener("click", function () {
    const url = this.getAttribute("href"); // 获取自定义标签的 href 属性
    if (url) {
        window.location.href = url; // 跳转到对应地址
    }
});

aElem.onmousemove = function(e) {

	const x = e.clientX - boundingClientRect.left
	const y = e.clientY - boundingClientRect.top
	
	const xc = boundingClientRect.width/2
	const yc = boundingClientRect.height/2
	
	const dx = x - xc
	const dy = y - yc
	
	docStyle.setProperty('--rx', `${ dy/-1 }deg`)
	docStyle.setProperty('--ry', `${ dx/10 }deg`)
	
}

aElem.onmouseleave = function(e) {
	
	docStyle.setProperty('--ty', '0')
	docStyle.setProperty('--rx', '0')
	docStyle.setProperty('--ry', '0')
	
}

aElem.onmousedown = function(e) {
	
	docStyle.setProperty('--tz', '-25px')
	
}

document.body.onmouseup = function(e) {
	
	docStyle.setProperty('--tz', '-12px')
	
}