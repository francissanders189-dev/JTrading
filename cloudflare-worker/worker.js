/**
 * JTrading 订阅服务 - Cloudflare Worker
 * 
 * 功能：接收用户订阅请求，将邮箱追加到私有 Gist，并发送确认邮件
 * 
 * 环境变量（在 Cloudflare Dashboard 中配置）：
 * - GIST_ID: Gist 的 ID（URL 中的那串字符）
 * - GIST_FILENAME: Gist 中的文件名（如 subscribers.txt）
 * - GITHUB_TOKEN: 具有 Gist 写入权限的 Personal Access Token
 * - ALLOWED_ORIGIN: 允许的前端域名（如 https://pear56.github.io）
 * - RESEND_API_KEY: Resend 邮件服务 API Key（可选，用于发送确认邮件）
 * - SENDER_EMAIL: 发件人邮箱（需在 Resend 验证，或用 onboarding@resend.dev 测试）
 */

export default {
  async fetch(request, env) {
    // CORS 预检请求
    if (request.method === 'OPTIONS') {
      return handleCORS(env);
    }

    // 只接受 POST 请求
    if (request.method !== 'POST') {
      return jsonResponse({ error: '只支持 POST 请求' }, 405, env);
    }

    try {
      // 解析请求体
      const contentType = request.headers.get('content-type') || '';
      let email = '';

      if (contentType.includes('application/json')) {
        const body = await request.json();
        email = body.email;
      } else if (contentType.includes('form')) {
        const formData = await request.formData();
        email = formData.get('email');
      } else {
        return jsonResponse({ error: '不支持的 Content-Type' }, 400, env);
      }

      // 验证邮箱格式
      if (!email || !isValidEmail(email)) {
        return jsonResponse({ error: '请提供有效的邮箱地址' }, 400, env);
      }

      // 读取当前 Gist 内容
      const gistData = await getGist(env);
      if (!gistData) {
        return jsonResponse({ error: '无法读取订阅列表' }, 500, env);
      }

      const currentContent = gistData.files[env.GIST_FILENAME]?.content || '';
      // 提取所有邮箱（忽略 [pending] 和 [confirmed] 标记）
      const allEmails = currentContent.split('\n')
        .map(line => line.replace(/^\[(pending|confirmed)\]\s*/i, '').trim().toLowerCase())
        .filter(Boolean);

      // 检查是否已订阅
      if (allEmails.includes(email.toLowerCase())) {
        return jsonResponse({ 
          success: true, 
          message: '您已经订阅过了，无需重复订阅' 
        }, 200, env);
      }

      // 追加新邮箱，标记为 [pending] 等待发送确认邮件
      const newContent = currentContent.trim() + '\n[pending] ' + email;
      const updated = await updateGist(env, newContent);

      if (updated) {
        return jsonResponse({ 
          success: true, 
          message: '订阅成功！确认邮件将在稍后发送到您的邮箱。' 
        }, 200, env);
      } else {
        return jsonResponse({ error: '订阅失败，请稍后重试' }, 500, env);
      }

    } catch (err) {
      console.error('Worker error:', err);
      return jsonResponse({ error: '服务器内部错误' }, 500, env);
    }
  }
};

/**
 * 验证邮箱格式
 */
function isValidEmail(email) {
  const re = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
  return re.test(email);
}

/**
 * 获取 Gist 内容
 */
async function getGist(env) {
  const response = await fetch(`https://api.github.com/gists/${env.GIST_ID}`, {
    headers: {
      'Authorization': `token ${env.GITHUB_TOKEN}`,
      'Accept': 'application/vnd.github.v3+json',
      'User-Agent': 'JTrading-Subscribe-Worker'
    }
  });

  if (response.ok) {
    return await response.json();
  }
  console.error('Failed to get gist:', response.status);
  return null;
}

/**
 * 更新 Gist 内容
 */
async function updateGist(env, newContent) {
  const response = await fetch(`https://api.github.com/gists/${env.GIST_ID}`, {
    method: 'PATCH',
    headers: {
      'Authorization': `token ${env.GITHUB_TOKEN}`,
      'Accept': 'application/vnd.github.v3+json',
      'User-Agent': 'JTrading-Subscribe-Worker',
      'Content-Type': 'application/json'
    },
    body: JSON.stringify({
      files: {
        [env.GIST_FILENAME]: {
          content: newContent
        }
      }
    })
  });

  return response.ok;
}

/**
 * CORS 预检响应
 */
function handleCORS(env) {
  return new Response(null, {
    status: 204,
    headers: {
      'Access-Control-Allow-Origin': env.ALLOWED_ORIGIN || '*',
      'Access-Control-Allow-Methods': 'POST, OPTIONS',
      'Access-Control-Allow-Headers': 'Content-Type',
      'Access-Control-Max-Age': '86400'
    }
  });
}

/**
 * JSON 响应
 */
function jsonResponse(data, status, env) {
  return new Response(JSON.stringify(data), {
    status,
    headers: {
      'Content-Type': 'application/json',
      'Access-Control-Allow-Origin': env.ALLOWED_ORIGIN || '*'
    }
  });
}

/**
 * 发送订阅确认邮件（使用 Resend API）
 */
async function sendConfirmationEmail(env, toEmail) {
  const senderEmail = env.SENDER_EMAIL || 'onboarding@resend.dev';
  const unsubscribeEmail = env.UNSUBSCRIBE_EMAIL || 'pear56@126.com';
  
  const htmlContent = `
<!DOCTYPE html>
<html>
<head>
  <meta charset="UTF-8">
  <style>
    body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; line-height: 1.6; color: #333; max-width: 600px; margin: 0 auto; padding: 20px; }
    .header { background: linear-gradient(135deg, #3498db 0%, #2980b9 100%); color: white; padding: 30px; border-radius: 10px 10px 0 0; text-align: center; }
    .content { background: #f9f9f9; padding: 30px; border: 1px solid #e0e0e0; }
    .footer { background: #2c3e50; color: #bdc3c7; padding: 20px; border-radius: 0 0 10px 10px; text-align: center; font-size: 12px; }
    .btn { display: inline-block; background: #3498db; color: white; padding: 12px 30px; text-decoration: none; border-radius: 5px; margin: 10px 0; }
    .unsubscribe { color: #95a5a6; text-decoration: none; }
    h1 { margin: 0; font-size: 24px; }
    .icon { font-size: 48px; margin-bottom: 10px; }
  </style>
</head>
<body>
  <div class="header">
    <div class="icon">📈</div>
    <h1>订阅成功！</h1>
  </div>
  <div class="content">
    <p>您好！</p>
    <p>感谢您订阅 <strong>JTrading RSI 监控</strong> 服务！</p>
    <p>从现在起，当 <strong>红利低波ETF (512890)</strong> 的 RSI 指标触发以下条件时，您将收到邮件通知：</p>
    <ul>
      <li>🟢 <strong>买入信号</strong>：RSI &lt; 40（超卖区域）</li>
      <li>🔴 <strong>卖出信号</strong>：RSI &gt; 70（超买区域）</li>
    </ul>
    <p style="text-align: center;">
      <a href="https://pear56.github.io/JTrading/" class="btn">查看实时监控面板</a>
    </p>
    <p style="color: #7f8c8d; font-size: 14px;">
      <em>提示：RSI 仅作为参考指标，投资需谨慎，建议结合其他分析方法。</em>
    </p>
  </div>
  <div class="footer">
    <p>JTrading - RSI 智能监控服务</p>
    <p>如需取消订阅，请<a href="mailto:${unsubscribeEmail}?subject=取消订阅 JTrading&body=请取消此邮箱的订阅：${toEmail}" class="unsubscribe">点击这里</a></p>
  </div>
</body>
</html>
  `.trim();

  const response = await fetch('https://api.resend.com/emails', {
    method: 'POST',
    headers: {
      'Authorization': `Bearer ${env.RESEND_API_KEY}`,
      'Content-Type': 'application/json'
    },
    body: JSON.stringify({
      from: `JTrading <${senderEmail}>`,
      to: [toEmail],
      subject: '✅ 订阅成功 - JTrading RSI 监控服务',
      html: htmlContent
    })
  });

  if (!response.ok) {
    const error = await response.text();
    throw new Error(`Resend API error: ${error}`);
  }
  
  console.log(`确认邮件已发送至: ${toEmail}`);
  return true;
}
