import { NextResponse } from 'next/server';

export const dynamic = 'force-dynamic';

export async function POST(request: Request) {
  try {
    const body = await request.json();
    const {
      type = 'PEAK_SHAVING',
      webhookUrl = process.env.ALERT_WEBHOOK_URL,
      peakKw = 885.5,
      thresholdKw = 800.0,
      overloadKw = 85.5,
      savings = 29925,
      actions = [],
    } = body;

    const targetUrl = webhookUrl || process.env.ALERT_WEBHOOK_URL;
    const nowTime = new Date().toLocaleTimeString();

    let slackPayload: any = {};

    if (type === 'GHOST_LOAD') {
      const {
        meterId = 'M001',
        wing = 'Wing A (Ground & 1st Flr)',
        building = 'Boys Hostel 1',
        observedKw = 26.8,
        excessKw = 14.4,
        elevatedMinutes = 48,
        costInr = 92,
        nilmCause = 'Likely Unattended AC (~4 units active)',
        wifiClients = 2,
      } = body;

      slackPayload = {
        username: 'GridPulse Hostel Ghost Load Intelligence',
        icon_emoji: ':bed:',
        attachments: [
          {
            color: '#f43f5e',
            title: `🚨 GHOST LOAD ALERT: ${building} - ${wing} [${meterId}]`,
            text: `*Unoccupied Room Waste Detected During Academic Hours:*\nSub-meter *${meterId}* in *${building}* has registered sustained elevated demand exceeding the robust Median baseline for *${elevatedMinutes} consecutive minutes*.\n\n<http://localhost:3000|Open GridPulse SCADA Console>`,
            fields: [
              { title: 'Observed Load', value: `${observedKw.toFixed(1)} kW`, short: true },
              { title: 'Excess Wasted Power', value: `+${excessKw.toFixed(1)} kW`, short: true },
              { title: 'Active Duration', value: `${elevatedMinutes} minutes`, short: true },
              { title: 'Estimated Waste Cost', value: `₹${costInr.toLocaleString()} INR`, short: true },
              { title: 'Wi-Fi AP Density', value: `${wifiClients} active devices (Strong Vacancy Evidence)`, short: true },
              { title: 'NILM Inferred Signature', value: nilmCause, short: true },
            ],
            footer: `GridPulse NILM Watchdog • Cooldown: 60m • Synced at ${nowTime}`,
            mrkdwn_in: ['text', 'fields'],
          },
        ],
      };
    } else if (type === 'PEAK_SHAVING') {
      const actionText = actions.length > 0
        ? actions.map((a: any) => `• *Tier ${a.tier} (${a.category}):* ${a.name} -> ${a.active_shed_kw} kW shed`).join('\n')
        : '• *Tier 1 (Soft Shedding):* Non-Critical Facilities & EV Setback -> 45.0 kW shed\n• *Tier 2 (Chiller Cycling):* Academic HVAC Duty Cycling -> 40.5 kW shed';

      slackPayload = {
        username: 'GridPulse AI Dispatcher',
        icon_emoji: ':battery:',
        attachments: [
          {
            color: overloadKw < 100 ? '#f59e0b' : '#ef4444',
            title: `IMPENDING PEAK DEMAND BREACH (+${overloadKw.toFixed(1)} kW)`,
            text: `*Automated Demand Response Triggered:*\nProjected campus peak is *${peakKw.toFixed(1)} kW*, breaching the contracted ceiling of *${thresholdKw.toFixed(1)} kW*.\n\n<http://localhost:3000|Open GridPulse Next.js Operations Portal>`,
            fields: [
              { title: 'Forecast Peak', value: `${peakKw.toFixed(1)} kW`, short: true },
              { title: 'Contract Threshold', value: `${thresholdKw.toFixed(1)} kW`, short: true },
              { title: 'Projected Overload', value: `+${overloadKw.toFixed(1)} kW`, short: true },
              { title: 'Potential Penalty Savings', value: `INR ${savings.toLocaleString()}`, short: true },
              { title: 'Active Countermeasures', value: actionText, short: false },
            ],
            footer: `GridPulse Real-Time Operations • Synced at ${nowTime}`,
            mrkdwn_in: ['text', 'fields'],
          },
        ],
      };
    } else {
      // SCADA Fault
      slackPayload = {
        username: 'GridPulse SCADA Watchdog',
        icon_emoji: ':rotating_light:',
        attachments: [
          {
            color: '#ef4444',
            title: 'SCADA Fault: CRITICAL VOLTAGE SAG [208.5V]',
            text: '*Grid Health Anomaly Detected:*\nSub-meter *M012* in building *BH2 (Hostels)* experienced nominal phase voltage drop below the 220V threshold.\n\n<http://localhost:3000|Open GridPulse SCADA Console>',
            fields: [
              { title: 'Meter ID', value: 'M012 (Smart Sub-Meter)', short: true },
              { title: 'Building Location', value: 'BH2 (Hostels)', short: true },
              { title: 'Observed Voltage', value: '208.50 V', short: true },
              { title: 'Standard Minimum', value: '220.00 V', short: true },
            ],
            footer: `GridPulse SCADA Watchdog • Synced at ${nowTime}`,
            mrkdwn_in: ['text', 'fields'],
          },
        ],
      };
    }

    const botToken = body.telegramBotToken || process.env.TELEGRAM_BOT_TOKEN;
    const chatId = body.telegramChatId || process.env.TELEGRAM_CHAT_ID;
    const isTelegramDirect = Boolean(botToken && chatId);
    const isTelegramUrl = Boolean(targetUrl && targetUrl.includes('api.telegram.org'));

    // Construct Telegram HTML message
    let telegramText = '';
    const portalUrl = process.env.NEXT_PUBLIC_SITE_URL || 'https://gridpulse-portal.vercel.app';

    if (type === 'GHOST_LOAD') {
      const {
        meterId = 'MTR_BH1_WA',
        wing = 'Wing A (Ground & 1st Flr)',
        building = 'Boys Hostel 1',
        observedKw = 26.8,
        excessKw = 14.4,
        elevatedMinutes = 48,
        costInr = 92,
        nilmCause = 'Likely Unattended AC (~4 units active)',
        wifiClients = 2,
      } = body;
      telegramText = [
        '🚨 <b>GRIDPULSE GHOST LOAD ALERT</b>',
        `📍 <b>Facility:</b> ${building} — ${wing} [<code>${meterId}</code>]`,
        `⚡ <b>Observed Demand:</b> ${observedKw.toFixed(1)} kW (<b>+${excessKw.toFixed(1)} kW excess</b>)`,
        `⏱️ <b>Unoccupied Duration:</b> ${elevatedMinutes} minutes`,
        `💰 <b>Estimated Wasted Cost:</b> ₹${costInr.toLocaleString()} INR`,
        `📶 <b>Wi-Fi Density:</b> ${wifiClients} connected devices (Strong Vacancy Evidence)`,
        `🔍 <b>NILM Diagnosis:</b> ${nilmCause}`,
        '',
        `🔗 <a href="${portalUrl}">Open GridPulse SCADA Console</a>`,
      ].join('\n');
    } else if (type === 'PEAK_SHAVING') {
      telegramText = [
        '⚠️ <b>GRIDPULSE PEAK DEMAND BREACH ALERT</b>',
        `🔥 <b>Forecast Peak:</b> ${peakKw.toFixed(1)} kW`,
        `📊 <b>Contract Threshold:</b> ${thresholdKw.toFixed(1)} kW`,
        `📈 <b>Projected Overload:</b> +${overloadKw.toFixed(1)} kW`,
        `💵 <b>Potential Penalty Avoidance:</b> ₹${savings.toLocaleString()} INR`,
        '',
        `🔗 <a href="${portalUrl}">Open GridPulse Operations Portal</a>`,
      ].join('\n');
    } else {
      telegramText = [
        '🚨 <b>GRIDPULSE SCADA FAULT ALERT</b>',
        '⚡ <b>Critical Voltage Sag Detected</b>',
        '',
        `🔗 <a href="${portalUrl}">Open GridPulse Operations Portal</a>`,
      ].join('\n');
    }

    // 1. Deliver via Telegram Bot API (supports broadcast to multiple comma-separated chat IDs)
    if (isTelegramDirect || isTelegramUrl) {
      const tgUrl = isTelegramUrl
        ? targetUrl!
        : `https://api.telegram.org/bot${botToken}/sendMessage`;

      const chatIds = isTelegramUrl
        ? [null]
        : String(chatId).split(',').map(s => s.trim()).filter(Boolean);

      const deliveryResults = await Promise.all(
        chatIds.map(async (cid) => {
          const tgPayload: any = {
            ...(cid ? { chat_id: cid } : {}),
            text: telegramText,
            parse_mode: 'HTML',
            disable_web_page_preview: false,
          };

          const res = await fetch(tgUrl, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(tgPayload),
          });
          const json = await res.json().catch(() => ({}));
          return { ok: res.ok, status: res.status, json, cid };
        })
      );

      const anyOk = deliveryResults.some(r => r.ok);
      const first = deliveryResults[0] || { ok: false, status: 500, json: {} };

      return NextResponse.json({
        success: anyOk,
        status: anyOk ? 'SENT_TELEGRAM' : `FAILED_TELEGRAM_${first.status}`,
        statusCode: first.status,
        message: anyOk
          ? `Successfully delivered incident alert to Telegram (${deliveryResults.filter(r => r.ok).length}/${deliveryResults.length} recipient${deliveryResults.length > 1 ? 's' : ''})!`
          : `Telegram delivery failed: ${first.json.description || 'Request failed'}`,
        channel: 'TELEGRAM',
        recipients: deliveryResults.map(r => ({ id: r.cid, ok: r.ok })),
        telegramText,
        payload: slackPayload,
        timestamp: new Date().toISOString(),
      });
    }

    // 2. Deliver via Slack / MS Teams / Discord Webhook
    if (targetUrl && targetUrl.startsWith('http')) {
      const slackRes = await fetch(targetUrl, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(slackPayload),
      });

      return NextResponse.json({
        success: slackRes.ok,
        status: slackRes.ok ? 'SENT_SLACK' : `FAILED_${slackRes.status}`,
        statusCode: slackRes.status,
        message: slackRes.ok ? 'Successfully delivered incident card to Slack.' : 'Slack delivery failed.',
        channel: 'SLACK',
        payload: slackPayload,
        timestamp: new Date().toISOString(),
      });
    }

    // 3. Fallback: Mock / Simulated Console
    return NextResponse.json({
      success: true,
      status: 'SIMULATED_SUCCESS',
      statusCode: 200,
      message: 'Dispatched to Mock Console (Configure TELEGRAM_BOT_TOKEN or ALERT_WEBHOOK_URL to send live notifications)',
      channel: 'SIMULATED',
      payload: slackPayload,
      telegramText,
      timestamp: new Date().toISOString(),
    });
  } catch (error: any) {
    console.error('Webhook dispatch error:', error);
    return NextResponse.json({ success: false, error: error.message }, { status: 500 });
  }
}
