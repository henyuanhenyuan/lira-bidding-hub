import { useState } from "react";

import { api } from "../core/api";
import { canManage, useAuth } from "../core/auth";
import { useAsync } from "../core/hooks";
import { Badge, Card, Empty, ErrorBox, Field, Page, Spinner, Table } from "../ui/kit";

interface User {
  username: string;
  role: string;
  created_at?: string;
}

interface Ops {
  scheduler: { enabled: boolean; mode: string };
  auth_enabled: boolean;
  backups: string[];
  collection: { collector: string; last_ok?: string; lag_hours?: number }[];
  freshness: { stale?: boolean; lag_hours?: number };
}

export default function Settings() {
  const { me } = useAuth();
  const editable = canManage(me);
  const { data, error, loading, reload } = useAsync(async () => {
    const [users, ops] = await Promise.all([
      api.get<User[]>("/api/users").catch(() => []),
      api.get<Ops>("/api/ops").catch(() => null),
    ]);
    return { users, ops };
  }, []);

  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [role, setRole] = useState("member");
  const [message, setMessage] = useState("");

  async function createUser() {
    setMessage("");
    try {
      await api.post("/api/users", { username, password, role });
      setUsername("");
      setPassword("");
      setMessage("账号已创建");
      await reload();
    } catch (err) {
      setMessage(err instanceof Error ? err.message : "创建失败");
    }
  }

  async function setRoleFor(user: User, next: string) {
    setMessage("");
    try {
      await api.patch(`/api/users/${encodeURIComponent(user.username)}`, { role: next });
      await reload();
    } catch (err) {
      setMessage(err instanceof Error ? err.message : "修改失败");
    }
  }

  if (loading && !data) return <Spinner />;
  if (error) return <ErrorBox message={error} />;
  if (!data) return null;

  return (
    <Page title="设置" desc="账号、运行环境与调度状态">
      {message && <div className="notice">{message}</div>}

      <div className="split">
        <Card title="账号" sub="管理员可创建账号与调整角色" flush>
          {(data.users ?? []).length === 0 ? (
            <Empty>未开启鉴权或没有账号数据。</Empty>
          ) : (
            <Table head={["账号", "角色", "操作"]}>
              {(data.users ?? []).map((user) => (
                <tr key={user.username}>
                  <td>{user.username}</td>
                  <td>
                    <Badge tone={user.role === "admin" ? "accent" : "neutral"}>{user.role}</Badge>
                  </td>
                  <td>
                    {editable ? (
                      <select
                        className="input"
                        value={user.role}
                        onChange={(event) => void setRoleFor(user, event.target.value)}
                      >
                        <option value="member">member</option>
                        <option value="manager">manager</option>
                        <option value="admin">admin</option>
                      </select>
                    ) : (
                      "—"
                    )}
                  </td>
                </tr>
              ))}
            </Table>
          )}
        </Card>

        <Card title="新建账号">
          {!editable && <p className="hint">当前角色无权创建账号。</p>}
          <Field label="账号">
            <input className="input" value={username} onChange={(event) => setUsername(event.target.value)} />
          </Field>
          <Field label="初始密码">
            <input
              className="input"
              type="password"
              value={password}
              onChange={(event) => setPassword(event.target.value)}
            />
          </Field>
          <Field label="角色">
            <select className="input" value={role} onChange={(event) => setRole(event.target.value)}>
              <option value="member">member</option>
              <option value="manager">manager</option>
              <option value="admin">admin</option>
            </select>
          </Field>
          <button className="btn" disabled={!editable} onClick={() => void createUser()}>
            创建
          </button>
        </Card>
      </div>

      <Card title="运行环境">
        {!data.ops ? (
          <Empty>运维信息仅管理员可见。</Empty>
        ) : (
          <dl className="kv">
            <dt>鉴权</dt>
            <dd>{data.ops.auth_enabled ? <Badge tone="ok">已开启</Badge> : <Badge tone="neutral">本地模式</Badge>}</dd>
            <dt>调度</dt>
            <dd>
              {data.ops.scheduler.mode}
              {data.ops.scheduler.enabled ? " · 运行中" : " · 关闭"}
            </dd>
            <dt>数据新鲜度</dt>
            <dd>
              {data.ops.freshness?.lag_hours != null ? Math.round(data.ops.freshness.lag_hours) : "—"}h
              {data.ops.freshness?.stale ? " · 已超时" : ""}
            </dd>
            <dt>备份</dt>
            <dd>{data.ops.backups?.slice(0, 2).join(" / ") || "—"}</dd>
          </dl>
        )}
      </Card>
    </Page>
  );
}
