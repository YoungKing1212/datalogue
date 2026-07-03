// Agent Team task stream client - Chat UI 和 Workbench 的唯一执行流入口。

export async function* streamAgentTeamTask(payload, { signal } = {}) {
  const res = await fetch('/api/agent-team/tasks/stream', {
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
      // 后端 SSE 可能包含 keepalive 或非 JSON 行，前端执行流忽略。
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
