const docStyle = document.documentElement.style
document.querySelectorAll("button-3d").forEach((aElem) => {
	const boundingClientRect = aElem.getBoundingClientRect()

	aElem.addEventListener("click", function (event) {
		const target = event.target.closest("button-3d"); // 确保点击的是 button-3d
		if (target) {
			// 如果元素有 `onclick` 属性，直接返回，执行自定义事件
			if (target.getAttribute("onclick")) {
				return;
			}
			// 否则执行默认跳转
			const url = target.getAttribute("href");
			console.log("button-3d clicked, default action:", url);
			if (url) {
				window.location.href = url;
			}
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
});
	