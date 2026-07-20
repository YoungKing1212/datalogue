// 对尚未接入真实后端的页面给出统一、可见的原型标识，避免演示数据被误认成生产数据。
export function PrototypeNotice({ compact = false, children }) {
  return (
    <div className={`prototype-notice${compact ? ' compact' : ''}`} role="status">
      <span className="prototype-notice-badge">功能原型</span>
      <span>{children || '当前内容为演示数据，操作不会写入生产系统。'}</span>
    </div>
  );
}
