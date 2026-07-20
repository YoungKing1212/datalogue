import { Button, Card, Form, Input, Typography, message } from 'antd';
import { useState } from 'react';
import { useLocation, useNavigate } from 'react-router-dom';

import { useAuth } from '../auth/auth-context';

export function LoginPage() {
  const [submitting, setSubmitting] = useState(false);
  const { user, login, changePassword } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();

  const from = location.state?.from?.pathname || '/';

  const onFinish = async (values) => {
    setSubmitting(true);
    try {
      const current = await login(values.username, values.password);
      if (!current.must_change_password) {
        navigate(from, { replace: true });
      }
    } catch (err) {
      message.error(err?.message || '登录失败，请检查账号密码');
    } finally {
      setSubmitting(false);
    }
  };

  const onPasswordChange = async (values) => {
    setSubmitting(true);
    try {
      await changePassword(values.currentPassword, values.newPassword);
      message.success('密码修改成功');
      navigate(from, { replace: true });
    } catch (err) {
      message.error(err?.message || '密码修改失败，请稍后重试');
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="login-page">
      <div className="login-surface" aria-hidden="true">
        <span className="login-glow login-glow-a" />
        <span className="login-glow login-glow-b" />
      </div>

      <div className="login-shell">
        <section className="login-brand-panel">
          <p className="login-brand-eyebrow">Datalogue Intelligence</p>
          <Typography.Title level={2} className="login-brand-title">
            数语
          </Typography.Title>
          <Typography.Paragraph className="login-brand-text">
            用一段自然语言，完成从业务问题到可解释结果的全流程问数。
          </Typography.Paragraph>

          <div className="login-brand-points">
            <div className="login-point">
              <span className="login-point-dot" />
              <span>多 Agent 协作拆解复杂问数任务</span>
            </div>
            <div className="login-point">
              <span className="login-point-dot" />
              <span>语义治理与 SQL 执行链路可回溯</span>
            </div>
            <div className="login-point">
              <span className="login-point-dot" />
              <span>工作台与对话上下文一致联动</span>
            </div>
          </div>
        </section>

        <Card className="login-card" variant="borderless">
          <Typography.Title level={3} className="login-title">
            {user?.must_change_password ? '设置新密码' : '欢迎登录'}
          </Typography.Title>
          <Typography.Paragraph type="secondary" className="login-subtitle">
            {user?.must_change_password
              ? '当前使用的是管理员签发的临时密码，修改后才能访问业务数据。'
              : '登录后可访问问数会话、工作台与数据治理能力。'}
          </Typography.Paragraph>

          {user?.must_change_password ? (
            <Form
              layout="horizontal"
              labelAlign="left"
              labelCol={{ flex: '124px' }}
              wrapperCol={{ flex: 'auto' }}
              colon={false}
              onFinish={onPasswordChange}
              autoComplete="off"
              size="large"
              className="login-form-inline"
            >
              <Form.Item
                label="当前临时密码"
                name="currentPassword"
                rules={[{ required: true, message: '请输入当前临时密码' }]}
              >
                <Input.Password autoComplete="current-password" />
              </Form.Item>
              <Form.Item
                label="新密码"
                name="newPassword"
                rules={[
                  { required: true, message: '请输入新密码' },
                  { min: 12, message: '新密码至少 12 位' },
                ]}
              >
                <Input.Password autoComplete="new-password" />
              </Form.Item>
              <Form.Item
                label="确认新密码"
                name="confirmPassword"
                dependencies={['newPassword']}
                rules={[
                  { required: true, message: '请再次输入新密码' },
                  ({ getFieldValue }) => ({
                    validator(_, value) {
                      return !value || value === getFieldValue('newPassword')
                        ? Promise.resolve()
                        : Promise.reject(new Error('两次输入的新密码不一致'));
                    },
                  }),
                ]}
              >
                <Input.Password autoComplete="new-password" />
              </Form.Item>
              <Button type="primary" htmlType="submit" block loading={submitting} className="login-submit-btn">
                修改密码并继续
              </Button>
            </Form>
          ) : (
          <Form
            layout="horizontal"
            labelAlign="left"
            labelCol={{ flex: '124px' }}
            wrapperCol={{ flex: 'auto' }}
            colon={false}
            onFinish={onFinish}
            autoComplete="off"
            size="large"
            className="login-form-inline"
          >
            <Form.Item
              label="用户名或邮箱"
              name="username"
              rules={[{ required: true, message: '请输入用户名或邮箱' }]}
            >
              <Input placeholder="例如：admin 或 user@example.com" />
            </Form.Item>
            <Form.Item
              label="密码"
              name="password"
              rules={[{ required: true, message: '请输入密码' }]}
            >
              <Input.Password placeholder="请输入密码" />
            </Form.Item>
            <Button type="primary" htmlType="submit" block loading={submitting} className="login-submit-btn">
              进入数语平台
            </Button>
          </Form>
          )}

          <Typography.Paragraph className="login-footnote" type="secondary">
            登录密码只通过 HTTPS 传输；非本机 HTTP 地址将拒绝登录。
          </Typography.Paragraph>
        </Card>
      </div>
    </div>
  );
}
