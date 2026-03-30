/**
 * LINE Webhook → 自営サーバ（RAG+LLM）→ replyMessage
 *
 * 初期設定は SETUP.md（PC: RAG + Gemini API、LINE: Messaging API は GAS のスクリプトプロパティ）。
 *
 * ■ 事前準備（スクリプト プロパティに登録・コードにベタ書きしない）
 *  エディタ: プロジェクトの設定（歯車）→「スクリプト プロパティ」で追加:
 *   LINE_CHANNEL_SECRET      … Messaging API のチャネルシークレット
 *   LINE_CHANNEL_ACCESS_TOKEN … チャネルアクセストークン（長期）
 *   BACKEND_SUGGEST_URL       … 例 https://（トンネルURL）/internal/suggest-replies
 *   INTERNAL_WEBHOOK_SECRET   … 自営サーバの .env INTERNAL_WEBHOOK_SECRET と同一の強いランダム文字列
 *   LINE_ALLOWED_USER_IDS    … 省略可。許可する userId をカンマ区切り（空なら全許可・非推奨）
 *   WEBHOOK_QUERY_TOKEN      … 推奨。推測困難な文字列。Webhook URL に ?token=値 を付与し GAS で照合
 *
 * ■ Webhook URL（LINE Developers）
 *   デプロイ後の URL の末尾に付与: ?execution=... は GAS 既定。追記例:
 *   https://script.google.com/macros/s/....../exec?token=（WEBHOOK_QUERY_TOKEN と同じ値）
 *
 * ■ 署名: GAS の Web アプリでは X-Line-Signature が渡らない場合がある。
 *   そのため WEBHOOK_QUERY_TOKEN による URL 秘匿を推奨。ヘッダが取れる環境では検証を行う。
 *
 * デプロイ: デプロイ → 新しいデプロイ → 種類「ウェブアプリ」
 *   次のユーザーとして実行: 自分 / アクセス: 全員（LINE からの POST のため）
 */

function doPost(e) {
  var props = PropertiesService.getScriptProperties();
  var queryToken = props.getProperty('WEBHOOK_QUERY_TOKEN');
  if (queryToken) {
    var q = (e.parameter && e.parameter.token) || '';
    if (q !== queryToken) {
      return ContentService.createTextOutput('Forbidden').setHttpStatus(403);
    }
  }

  if (!e.postData || !e.postData.contents) {
    return ContentService.createTextOutput('Bad Request').setHttpStatus(400);
  }

  var body = e.postData.contents;

  var lineSig = null;
  try {
    if (e.headers) {
      lineSig = e.headers['X-Line-Signature'] || e.headers['x-line-signature'] || null;
    }
  } catch (err) {}

  var secret = props.getProperty('LINE_CHANNEL_SECRET');
  if (lineSig && secret) {
    if (!verifyLineSignature_(body, secret, lineSig)) {
      return ContentService.createTextOutput('Unauthorized').setHttpStatus(401);
    }
  }

  var data;
  try {
    data = JSON.parse(body);
  } catch (ex) {
    return ContentService.createTextOutput('Bad Request').setHttpStatus(400);
  }

  var events = data.events || [];
  for (var i = 0; i < events.length; i++) {
    handleLineEvent_(events[i], props);
  }

  return ContentService.createTextOutput('OK');
}

/**
 * LINE公式と同じ HMAC-SHA256(Base64)
 */
function verifyLineSignature_(bodyString, channelSecret, xLineSignature) {
  var sig = Utilities.computeHmacSha256Signature(bodyString, channelSecret);
  var expected = Utilities.base64Encode(sig);
  return expected === xLineSignature;
}

function handleLineEvent_(ev, props) {
  if (!ev || ev.type !== 'message') return;
  var msg = ev.message;
  if (!msg || msg.type !== 'text') return;

  var src = ev.source || {};
  var userId = src.userId || '';

  var allow = props.getProperty('LINE_ALLOWED_USER_IDS');
  if (allow && allow.trim()) {
    var set = {};
    allow.split(',').forEach(function (s) {
      var t = s.trim();
      if (t) set[t] = true;
    });
    if (!set[userId]) return;
  }

  var replyToken = ev.replyToken;
  var userText = (msg.text || '').trim();
  if (!replyToken || !userText) return;

  var backendUrl = props.getProperty('BACKEND_SUGGEST_URL');
  var internalSecret = props.getProperty('INTERNAL_WEBHOOK_SECRET');
  if (!backendUrl || !internalSecret) {
    return;
  }

  var payload = JSON.stringify({
    user_text: userText,
    line_user_id: userId,
  });

  var res = UrlFetchApp.fetch(backendUrl, {
    method: 'post',
    contentType: 'application/json',
    headers: {
      Authorization: 'Bearer ' + internalSecret,
    },
    payload: payload,
    muteHttpExceptions: true,
  });

  var code = res.getResponseCode();
  var resBody = res.getContentText();
  if (code !== 200) {
    replyLine_(props.getProperty('LINE_CHANNEL_ACCESS_TOKEN'), replyToken,
      '【エラー】サーバとの通信に失敗しました（' + code + '）。時間をおいて再試行してください。');
    return;
  }

  var parsed;
  try {
    parsed = JSON.parse(resBody);
  } catch (ex) {
    replyLine_(props.getProperty('LINE_CHANNEL_ACCESS_TOKEN'), replyToken,
      '【エラー】サーバの応答が不正です。管理者に連絡してください。');
    return;
  }

  var text = parsed.text || '';
  if (!text) {
    text = '返信案を生成できませんでした。';
  }

  replyLine_(props.getProperty('LINE_CHANNEL_ACCESS_TOKEN'), replyToken, text);
}

function replyLine_(accessToken, replyToken, text) {
  if (!accessToken) return;
  var url = 'https://api.line.me/v2/bot/message/reply';
  var maxLen = 4500;
  var parts = [];
  for (var i = 0; i < text.length; i += maxLen) {
    parts.push(text.substring(i, i + maxLen));
  }
  if (parts.length > 5) parts = parts.slice(0, 5);

  var messages = parts.map(function (p) {
    return { type: 'text', text: p };
  });

  var options = {
    method: 'post',
    contentType: 'application/json',
    headers: { Authorization: 'Bearer ' + accessToken },
    payload: JSON.stringify({
      replyToken: replyToken,
      messages: messages,
    }),
    muteHttpExceptions: true,
  };

  UrlFetchApp.fetch(url, options);
}
