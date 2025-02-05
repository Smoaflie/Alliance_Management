let userName = ""
$("document").ready(start());
function start()
{ 
  auth_config = getQueryVariable("appId");
  // appId = getQueryVariable("appId");
  // timestamp = getQueryVariable("timestamp");
  // noncestr = getQueryVariable("noncestr");
  // signature = getQueryVariable("signature");
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
}
function getQueryVariable(variable)
{
    var query = window.location.search.substring(1);
    var vars = query.split("&");
    for (var i=0;i<vars.length;i++) {
        var pair = vars[i].split("=");
        if(pair[0] == variable){return pair[1];}
    }
    return(false);
}
function inputItemID()
{
    window.h5sdk.ready(() => {
        tt.showPrompt({
            "title": "请在这里键入教务处课表页项JSESSIONID的cookie值",
            "placeholder": "示例格式:16FDF21114251A4BBF40F5AEE70XXXXX",
            "maxLength": 50,
            "confirmText": "确定",
            "cancelText": "取消",
            success(res) {
              console.log(JSON.stringify(res));
            },
            fail(res) {
              console.log(`showPrompt fail: ${JSON.stringify(res)}`);
            }
        });
    })
}