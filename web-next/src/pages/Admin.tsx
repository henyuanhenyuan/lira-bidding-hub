import { useState } from "react";

import { api } from "../api";
import { useAuth } from "../auth";
import { Card, Empty, ErrorBox, Loader, PageHead } from "../components/ui";
import { formatTs } from "../format";
import { useAsync } from "../hooks";
import { ROLE_TEXT } from "../labels";
import type { Role, UserRow } from "../types";

const ROLES: Role[] = ["admin", "manager", "member"];

export default function Admin() {
  const { me } = useAuth();
  const isAdmin = me?.role === "admin";
  const { data, error, loading, reload } = useAsync(
    () => (isAdmin ? api.get<UserRow[]>("/api/users") : Promise.resolve(null)),
    [isAdmin],
  );

  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [role, setRole] = useState<Role>("member");
  const [message, setMessage] = useState("");
  const [oldPassword, setOldPassword] = useState("");
  const [newPassword, setNewPassword] = useState("");

  if (!isAdmin) {
    return (
      <>
        <PageHead title="账号" sub="仅管理员可见" />
        <Empty>当前账号没有管理权限。</Empty>
      </>
    );
  }

  if (loading && !data) return <Loader label="载入账号…" />;
  if (error && !data) return <ErrorBox message={error} onRetry={reload} />;

  async function createUser() {
    setMessage("");
    try {
      await api.post("/api/users", {
        username: username.trim(),
        password,
        role,
      });
      setUsername("");
      setPassword("");
      setRole("member");
      setMessage("账号已创建");
      await reload();
    } catch (err) {
      setMessage(err instanceof Error ? err.message : "创建失败");
    }
  }

  async function changeRole(name: string, next: Role) {
    try {
      await api.patch(`/api/users/${encodeURIComponent(name)}`, { role: next });
      await reload();
    } catch (err) {
      setMessage(err instanceof Error ? err.message : "调整失败");
    }
  }

  async function changePassword() {
    if (!me) return;
    setMessage("");
    try {
      await api.post(`/api/users/${encodeURIComponent(me.username)}/password`, {
        old_password: oldPassword || null,
        new_password: newPassword,
      });
      setOldPassword("");
      setNewPassword("");
      setMessage("密码已更新");
    } catch (err) {
      setMessage(err instanceof Error ? err.message : "修改失败");
    }
  }

  return (
    <>
      <PageHead title="账号" sub="角色决定能不能审批、能不能看采集与运维" />

      {message && <div className="notice">{message}</div>}

      <Card title="账号列表">
        {!data || data.length === 0 ? (
          <Empty>还没有账号。开启鉴权后会自动创建 admin。</Empty>
        ) : (
          <div className="table-wrap">
            <table className="table">
              <thead>
                <tr>
                  <th>用户名</th>
                  <th>角色</th>
                  <th>创建时间</th>
                </tr>
              </thead>
              <tbody>
                {data.map((user) => (
                  <tr key={user.username}>
                    <td>{user.username}</td>
                    <td>
                      <select
                        className="select"
                        value={user.role}
                        onChange={(event) =>
                          void changeRole(user.username, event.target.value as Role)
                        }
                      >
                        {ROLES.map((item) => (
                          <option key={item} value={item}>
                            {ROLE_TEXT[item]}
                          </option>
                        ))}
                      </select>
                    </td>
                    <td className="num">{formatTs(user.created_at)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>

      <div className="detail-grid">
        <Card title="新建账号" sub="新账号会立刻生效">
          <div className="form-grid">
            <label>
              用户名
              <input
                className="input"
                value={username}
                onChange={(event) => setUsername(event.target.value)}
              />
            </label>
            <label>
              密码
              <input
                className="input"
                type="password"
                value={password}
                onChange={(event) => setPassword(event.target.value)}
              />
            </label>
            <label>
              角色
              <select
                className="select"
                value={role}
                onChange={(event) => setRole(event.target.value as Role)}
              >
                {ROLES.map((item) => (
                  <option key={item} value={item}>
                    {ROLE_TEXT[item]}
                  </option>
                ))}
              </select>
            </label>
          </div>
          <button className="btn" onClick={() => void createUser()}>
            创建
          </button>
        </Card>

        <Card title="修改我的密码" sub="至少 6 位；修改后可继续使用当前会话">
          <div className="form-grid">
            <label>
              原密码
              <input
                className="input"
                type="password"
                value={oldPassword}
                onChange={(event) => setOldPassword(event.target.value)}
              />
            </label>
            <label>
              新密码
              <input
                className="input"
                type="password"
                value={newPassword}
                onChange={(event) => setNewPassword(event.target.value)}
              />
            </label>
          </div>
          <button className="btn" onClick={() => void changePassword()}>
            更新密码
          </button>
        </Card>
      </div>
    </>
  );
}
