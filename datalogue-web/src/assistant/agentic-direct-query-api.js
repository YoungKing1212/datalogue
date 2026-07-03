// AgenticLeadAgent direct-query stream client - 仅供已有直连问数入口消费。

export async function* streamAgenticDirectQuery(payload, { signal } = {}) {
  const res = await fetch('/api/agentic-lead-agent/direct-query/stream', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
    signal,
  });
  if (!res.ok) throw new Error(`HTTP ${res.status}: ${res.statusText}`);

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = '';
  const parseDataLine = (line) => {
    if (!line.startsWith('data:')) return null;
    const body = line.slice(5).trim();
    if (!body) return null;
    try {
      return JSON.parse(body);
    } catch {
      // SSE 中的 keepalive 或非 JSON 行不进入聊天消息流。
      return null;
    }
  };

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const lines = buffer.split('\n');
    buffer = lines.pop();
    for (const line of lines) {
      const event = parseDataLine(line);
      if (event) yield event;
    }
  }
  const tailEvent = parseDataLine(buffer);
  if (tailEvent) yield tailEvent;
}
