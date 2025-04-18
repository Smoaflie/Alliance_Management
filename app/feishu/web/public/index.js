let lang = window.navigator.language;
let userInfo = {}
let auth_config = {}
$("document").ready(apiAuth());

function apiAuth() {
  console.log("start apiAuth");
  if (!window.h5sdk) {
    console.log("invalid h5sdk");
    alert("please open in feishu");
    return;
  }

  // 调用config接口的当前网页url
  const url = encodeURIComponent(location.href.split("#")[0]);
  console.log("接入方前端将需要鉴权的url发给接入方服务端,url为:", url);
  // 向接入方服务端发起请求，获取鉴权参数（appId、timestamp、nonceStr、signature）
  fetch(`./get_config_parameters?url=${url}`)
    .then((response) =>
      response.json().then((res) => {
        auth_config = res;
        console.log(
          "接入方服务端返回给接入方前端的结果(前端调用config接口的所需参数):", res
        );
        // 通过error接口处理API验证失败后的回调
        window.h5sdk.error((err) => {
          throw ("h5sdk error:", JSON.stringify(err));
        });
        // 调用config接口进行鉴权
        window.h5sdk.config({
          appId: auth_config.appid,
          timestamp: auth_config.timestamp,
          nonceStr: auth_config.noncestr,
          signature: auth_config.signature,
          jsApiList: [],
          //鉴权成功回调
          onSuccess: (res) => {
            console.log(`config success: ${JSON.stringify(res)}`);
          },
          //鉴权失败回调
          onFail: (err) => {
            throw `config failed: ${JSON.stringify(err)}`;
          },
        });
        // 完成鉴权后，便可在 window.h5sdk.ready 里调用 JSAPI
        window.h5sdk.ready(() => {
          // window.h5sdk.ready回调函数在环境准备就绪时触发
          // 调用 getUserInfo API 获取已登录用户的基本信息，详细文档参见https://open.feishu.cn/document/uYjL24iN/ucjMx4yNyEjL3ITM
          tt.getUserInfo({
            // getUserInfo API 调用成功回调
            success(res) {
              console.log(`getUserInfo success: ${JSON.stringify(res)}`);
              // 单独定义的函数showUser，用于将用户信息展示在前端页面上
              showMenu(res.userInfo);
              userInfo = res.userInfo;
            },
            // getUserInfo API 调用失败回调
            fail(err) {
              console.log(`getUserInfo failed:`, JSON.stringify(err));
            },
          });
          // 调用 showToast API 弹出全局提示框，详细文档参见https://open.feishu.cn/document/uAjLw4CM/uYjL24iN/block/api/showtoast
          tt.showToast({
            title: "鉴权成功",
            icon: "success",
            duration: 3000,
            success(res) {
              console.log("showToast 调用成功", res.errMsg);
            },
            fail(res) {
              console.log("showToast 调用失败", res.errMsg);
            },
            complete(res) {
              console.log("showToast 调用结束", res.errMsg);
            },
          });
        });
      })
    )
    .catch(function (e) {
      console.error(e);
    });
}

function getTimePeriod() {
  const hour = new Date().getHours(); // 获取当前小时

  if (hour >= 5 && hour < 12) {
    return "早上好"; // 5:00 - 11:59
  } else if (hour >= 17 && hour < 23) {
    return "傍晚好"; // 17:00 - 19:59
  } else if (hour >= 0 && hour < 5 || hour >= 23) {
    return "深夜好"; // 23:00 - 4:59
  } else {
    return "下午好"; // 12:00 - 16:59
  }
}

function showMenu(res) {
  // 展示用户信息
  $(".loader").addClass("hidden");  // 让加载动画淡出
  setTimeout(() => {
    $(".loader").hide();  // 确保动画结束后隐藏
    $("#avatar").html(
      `<img src="${res.avatarUrl}" width="100%" height=""100%/>`
    );
    $("#hello-text").text(getTimePeriod() + ", " + res.nickName); // 让文字渐显
    $("#hello-text").removeClass("hidden");
    $("#menu").removeClass("hidden");
    $('.container').addClass('is-loaded');
  }, 1000); // 等待1秒（与 CSS 过渡时间一致）
}

function inputCookie() {
  tt.showPrompt({
    "title": "请键入教务处课表页cookie值",
    "placeholder": "示例格式:16FDF21114251A4BBF40F5AEE70XXXXX",
    "maxLength": 50,
    "confirmText": "确定",
    "cancelText": "取消",
    success(res) {
      console.log(JSON.stringify(res));
      if (res.confirm) {
        fetch(`./class_schedule?cookie=${res.inputValue}&userName=${userInfo.nickName}`,{method:"POST"})
        .then(response => {
          console.log(response)
          if (!response.ok) {  // 处理 400、500 等错误
            throw new Error(`HTTP error! Status: ${response.status}`);
          }
          response.json()})
        .then(data => {
          console.log('Success:', data);
          tt.showToast({
            title: "更新成功",
            icon: "success",
            duration: 3000,
          });})
        .catch(error => {
          console.error('Error:', error);
          tt.showToast({
            title: "更新失败，请检查cookie",
            icon: "error",
            duration: 3000,
          });});
      }
    },
    fail(res) {
      console.log(`showPrompt fail: ${JSON.stringify(res)}`);
    }
  });
}