import { Button, Card, Form, Input, Modal, Popconfirm, Select, Space, Table, Tag, Tooltip, message, Typography } from 'antd';
import { useEffect, useMemo, useState } from 'react';

import {
  createUserAccount,
  deleteUserAccount,
  listUserAccounts,
  resetUserAccountPassword,
  updateUserAccount,
} from '../api/client';
import { useAuth } from '../auth/auth-context';
import { Icon } from './icons';

export function UserCreateScreen() {
  const [createForm] = Form.useForm();
  const [editForm] = Form.useForm();
  const { user: currentUser } = useAuth();
  const [submitting, setSubmitting] = useState(false);
  const [actionLoading, setActionLoading] = useState(false);
  const [loadingUsers, setLoadingUsers] = useState(false);
  const [users, setUsers] = useState([]);
  const [createOpen, setCreateOpen] = useState(false);
  const [editOpen, setEditOpen] = useState(false);
  const [resetOpen, setResetOpen] = useState(false);
  const [activeUser, setActiveUser] = useState(null);
  const [keyword, setKeyword] = useState('');
  const [roleFilter, setRoleFilter] = useState('all');
  const [statusFilter, setStatusFilter] = useState('all');

  const loadUsers = async () => {
    setLoadingUsers(true);
    try {
      const data = await listUserAccounts();
      setUsers(Array.isArray(data) ? data : []);
    } catch (err) {
      message.error(err?.message || '获取用户列表失败，请稍后重试');
    } finally {
      setLoadingUsers(false);
    }
  };

  useEffect(() => {
    loadUsers();
  }, []);

  const filteredUsers = useMemo(() => {
    const normalizedKeyword = keyword.trim().toLowerCase();
    return users.filter((item) => {
      const roleKey = item.is_superuser ? 'super' : item.role === 'admin' ? 'admin' : 'user';
      const statusKey = item.is_active ? 'active' : 'inactive';
      const hitKeyword =
        !normalizedKeyword ||
        String(item.username || '').toLowerCase().includes(normalizedKeyword) ||
        String(item.full_name || '').toLowerCase().includes(normalizedKeyword) ||
        String(item.email || '').toLowerCase().includes(normalizedKeyword);
      const hitRole = roleFilter === 'all' || roleFilter === roleKey;
      const hitStatus = statusFilter === 'all' || statusFilter === statusKey;
      return hitKeyword && hitRole && hitStatus;
    });
  }, [users, keyword, roleFilter, statusFilter]);

  const onFinish = async (values) => {
    setSubmitting(true);
    try {
      await createUserAccount({
        username: values.username,
        password: values.password,
        email: values.email || null,
        full_name: values.fullName || null,
      });
      message.success(`用户 ${values.username} 创建成功`);
      createForm.resetFields();
      setCreateOpen(false);
      await loadUsers();
    } catch (err) {
      message.error(err?.message || '创建用户失败，请稍后重试');
    } finally {
      setSubmitting(false);
    }
  };

  const openEditModal = (record) => {
    setActiveUser(record);
    editForm.setFieldsValue({
      fullName: record.full_name || '',
      email: record.email || '',
      role: record.role || 'user',
      isActive: Boolean(record.is_active),
    });
    setEditOpen(true);
  };

  const onEditFinish = async (values) => {
    if (!activeUser) return;
    setActionLoading(true);
    try {
      await updateUserAccount(activeUser.id, {
        full_name: values.fullName || null,
        email: values.email || null,
        role: values.role,
        is_active: values.isActive,
      });
      message.success(`用户 ${activeUser.username} 已更新`);
      setEditOpen(false);
      setActiveUser(null);
      editForm.resetFields();
      await loadUsers();
    } catch (err) {
      message.error(err?.message || '更新用户失败，请稍后重试');
    } finally {
      setActionLoading(false);
    }
  };

  const openResetModal = (record) => {
    setActiveUser(record);
    setResetOpen(true);
  };

  const onConfirmResetPassword = async () => {
    if (!activeUser) return;
    setActionLoading(true);
    try {
      await resetUserAccountPassword(activeUser.id);
      message.success(`用户 ${activeUser.username} 密码已重置为 ${activeUser.username}@123456`);
      setResetOpen(false);
      setActiveUser(null);
    } catch (err) {
      message.error(err?.message || '重置密码失败，请稍后重试');
    } finally {
      setActionLoading(false);
    }
  };

  const onDeleteUser = async (record) => {
    setActionLoading(true);
    try {
      await deleteUserAccount(record.id);
      message.success(`用户 ${record.username} 已删除`);
      await loadUsers();
    } catch (err) {
      message.error(err?.message || '删除用户失败，请稍后重试');
    } finally {
      setActionLoading(false);
    }
  };

  const columns = [
    {
      title: '用户名',
      dataIndex: 'username',
      key: 'username',
    },
    {
      title: '姓名',
      dataIndex: 'full_name',
      key: 'full_name',
      render: (value) => value || '-',
    },
    {
      title: '邮箱',
      dataIndex: 'email',
      key: 'email',
      render: (value) => value || '-',
    },
    {
      title: '角色',
      key: 'role',
      width: 120,
      render: (_, record) => {
        if (record.is_superuser) {
          return <Tag color="gold">超级管理员</Tag>;
        }
        if (record.role === 'admin') {
          return <Tag color="processing">管理员</Tag>;
        }
        return <Tag>普通用户</Tag>;
      },
    },
    {
      title: '状态',
      dataIndex: 'is_active',
      key: 'is_active',
      width: 120,
      render: (value) => (value ? <Tag color="success">启用</Tag> : <Tag color="default">禁用</Tag>),
    },
    {
      title: '操作',
      key: 'actions',
      width: 168,
      render: (_, record) => {
        const isSelf = currentUser?.id === record.id;
        const canDelete = !record.is_superuser && !isSelf;
        return (
          <Space size={6} className="um-action-group">
            <Tooltip title="编辑用户" placement="top">
              <Button
                type="text"
                size="small"
                className="um-action-btn"
                onClick={() => openEditModal(record)}
                icon={<Icon name="edit" />}
              />
            </Tooltip>

            <Tooltip title="重置密码" placement="top">
              <Button
                type="text"
                size="small"
                className="um-action-btn"
                onClick={() => openResetModal(record)}
                icon={<Icon name="refresh" />}
              />
            </Tooltip>

            <Popconfirm
              title="确认删除该用户吗？"
              description="删除后将无法恢复。"
              okText="删除"
              cancelText="取消"
              onConfirm={() => onDeleteUser(record)}
              disabled={!canDelete}
            >
              <Tooltip title={canDelete ? '删除用户' : '当前用户不可删除'} placement="top">
                <Button
                  type="text"
                  size="small"
                  danger
                  disabled={!canDelete}
                  className="um-action-btn"
                  icon={<Icon name="trash" />}
                />
              </Tooltip>
            </Popconfirm>
          </Space>
        );
      },
    },
  ];

  return (
    <div className="user-manage-wrap">
      <Card className="user-manage-card" variant="borderless">
        <div className="user-manage-header">
          <div>
            <Typography.Title level={3} className="user-manage-title">
              用户管理
            </Typography.Title>
            <Typography.Paragraph className="user-manage-subtitle" type="secondary">
              管理平台用户账号，支持查看已有用户并快速创建新用户。
            </Typography.Paragraph>
          </div>
        </div>

        <div className="user-manage-toolbar">
          <Input.Search
            allowClear
            placeholder="按用户名/姓名/邮箱搜索"
            value={keyword}
            onChange={(event) => setKeyword(event.target.value)}
            className="user-manage-search"
          />
          <Select
            value={roleFilter}
            onChange={setRoleFilter}
            options={[
              { value: 'all', label: '全部角色' },
              { value: 'super', label: '超级管理员' },
              { value: 'admin', label: '管理员' },
              { value: 'user', label: '普通用户' },
            ]}
            className="user-manage-filter"
          />
          <Select
            value={statusFilter}
            onChange={setStatusFilter}
            options={[
              { value: 'all', label: '全部状态' },
              { value: 'active', label: '启用' },
              { value: 'inactive', label: '禁用' },
            ]}
            className="user-manage-filter"
          />

          <Button className="user-manage-create-btn" onClick={() => setCreateOpen(true)}>
            <Icon name="plus" />
            新建用户
          </Button>
        </div>

        <Table
          rowKey="id"
          columns={columns}
          dataSource={filteredUsers}
          loading={loadingUsers}
          pagination={{ pageSize: 10, showSizeChanger: false }}
        />

        <Modal
          title="新建用户"
          open={createOpen}
          onCancel={() => {
            if (!submitting) {
              setCreateOpen(false);
              createForm.resetFields();
            }
          }}
          footer={null}
          destroyOnClose
        >
          <Form
            form={createForm}
            layout="vertical"
            onFinish={onFinish}
            autoComplete="off"
            size="large"
          >
            <Form.Item
              label="用户名"
              name="username"
              rules={[
                { required: true, message: '请输入用户名' },
                { min: 3, message: '用户名至少 3 个字符' },
              ]}
            >
              <Input placeholder="例如：sales_admin" />
            </Form.Item>

            <Form.Item
              label="邮箱（可选）"
              name="email"
              rules={[{ type: 'email', message: '请输入合法邮箱地址' }]}
            >
              <Input placeholder="例如：user@company.com" />
            </Form.Item>

            <Form.Item label="姓名（可选）" name="fullName">
              <Input placeholder="例如：张三" />
            </Form.Item>

            <Form.Item
              label="初始密码"
              name="password"
              rules={[
                { required: true, message: '请输入初始密码' },
                { min: 6, message: '密码至少 6 位' },
              ]}
            >
              <Input.Password placeholder="请输入初始密码" />
            </Form.Item>

            <Form.Item
              label="确认密码"
              name="confirmPassword"
              dependencies={['password']}
              rules={[
                { required: true, message: '请确认密码' },
                ({ getFieldValue }) => ({
                  validator(_, value) {
                    if (!value || getFieldValue('password') === value) {
                      return Promise.resolve();
                    }
                    return Promise.reject(new Error('两次输入密码不一致'));
                  },
                }),
              ]}
            >
              <Input.Password placeholder="请再次输入密码" />
            </Form.Item>

            <div className="user-create-actions">
              <Space>
                <Button
                  onClick={() => {
                    if (!submitting) {
                      setCreateOpen(false);
                      createForm.resetFields();
                    }
                  }}
                >
                  取消
                </Button>
                <Button type="primary" htmlType="submit" loading={submitting}>
                  创建用户
                </Button>
              </Space>
            </div>
          </Form>
        </Modal>

        <Modal
          title={`编辑用户：${activeUser?.username || ''}`}
          open={editOpen}
          onCancel={() => {
            if (!actionLoading) {
              setEditOpen(false);
              setActiveUser(null);
              editForm.resetFields();
            }
          }}
          footer={null}
          destroyOnClose
        >
          <Form
            form={editForm}
            layout="vertical"
            onFinish={onEditFinish}
            autoComplete="off"
            size="large"
          >
            <Form.Item label="用户名">
              <Input value={activeUser?.username || ''} disabled />
            </Form.Item>

            <Form.Item label="姓名" name="fullName">
              <Input placeholder="例如：张三" />
            </Form.Item>

            <Form.Item label="邮箱" name="email" rules={[{ type: 'email', message: '请输入合法邮箱地址' }]}>
              <Input placeholder="例如：user@company.com" />
            </Form.Item>

            <Form.Item label="角色" name="role" rules={[{ required: true, message: '请选择角色' }]}>
              <Select
                options={[
                  { value: 'admin', label: '管理员' },
                  { value: 'user', label: '普通用户' },
                ]}
                disabled={Boolean(activeUser?.is_superuser)}
              />
            </Form.Item>

            <Form.Item label="账号状态" name="isActive" rules={[{ required: true, message: '请选择状态' }]}>
              <Select
                options={[
                  { value: true, label: '启用' },
                  { value: false, label: '禁用' },
                ]}
                disabled={Boolean(activeUser?.is_superuser)}
              />
            </Form.Item>

            {activeUser?.is_superuser && (
              <Typography.Text type="secondary">超级管理员账号不支持降级或禁用。</Typography.Text>
            )}

            <div className="user-create-actions" style={{ marginTop: 14 }}>
              <Space>
                <Button
                  onClick={() => {
                    if (!actionLoading) {
                      setEditOpen(false);
                      setActiveUser(null);
                      editForm.resetFields();
                    }
                  }}
                >
                  取消
                </Button>
                <Button type="primary" htmlType="submit" loading={actionLoading}>
                  保存修改
                </Button>
              </Space>
            </div>
          </Form>
        </Modal>

        <Modal
          title={`重置密码：${activeUser?.username || ''}`}
          open={resetOpen}
          onCancel={() => {
            if (!actionLoading) {
              setResetOpen(false);
              setActiveUser(null);
            }
          }}
          footer={null}
          destroyOnClose
        >
          <Typography.Paragraph style={{ marginBottom: 12 }}>
            重置后该用户密码将变更为：
            <Typography.Text strong>{activeUser?.username || ''}@123456</Typography.Text>
          </Typography.Paragraph>
          <Typography.Paragraph type="secondary" style={{ marginBottom: 18 }}>
            请通知用户首次登录后尽快修改密码。
          </Typography.Paragraph>

          <div className="user-create-actions">
            <Space>
              <Button
                onClick={() => {
                  if (!actionLoading) {
                    setResetOpen(false);
                    setActiveUser(null);
                  }
                }}
              >
                取消
              </Button>
              <Button type="primary" onClick={onConfirmResetPassword} loading={actionLoading}>
                确认重置
              </Button>
            </Space>
          </div>
        </Modal>
      </Card>
    </div>
  );
}
