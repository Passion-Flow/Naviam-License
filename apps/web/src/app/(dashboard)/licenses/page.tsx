"use client";

import { useState, useEffect, useCallback } from "react";
import { Plus, Search, Filter, Loader2, Copy, Check, RefreshCw, Ban, Trash2, AlertTriangle } from "lucide-react";
import Modal from "@/components/Modal";
import {
  api,
  type License,
  type Customer,
  type Product,
  type IssueLicenseRequest,
  type IssueLicenseResponse,
  type RenewLicenseResponse,
} from "@/lib/api";

const STATUS_MAP: Record<string, { label: string; cls: string }> = {
  draft: { label: "草稿", cls: "badge-neutral" },
  issued: { label: "已签发", cls: "badge-info" },
  active: { label: "生效中", cls: "badge-success" },
  expired: { label: "已过期", cls: "badge-warning" },
  grace: { label: "宽限期", cls: "badge-warning" },
  revoked: { label: "已吊销", cls: "badge-danger" },
  sunset: { label: "已失效", cls: "badge-neutral" },
};

function formatDate(iso: string | null) {
  if (!iso) return "—";
  const d = new Date(iso);
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")} ${String(d.getHours()).padStart(2, "0")}:${String(d.getMinutes()).padStart(2, "0")}`;
}

export default function LicensesPage() {
  const [licenses, setLicenses] = useState<License[]>([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState("");
  const [statusFilter, setStatusFilter] = useState<string>("");
  const [error, setError] = useState("");

  const [modalOpen, setModalOpen] = useState(false);
  const [customers, setCustomers] = useState<Customer[]>([]);
  const [products, setProducts] = useState<Product[]>([]);
  const [modalLoading, setModalLoading] = useState(false);
  const [modalError, setModalError] = useState("");

  const [cloudId, setCloudId] = useState("");
  const [customerId, setCustomerId] = useState("");
  const [productId, setProductId] = useState("");
  const [expiresAt, setExpiresAt] = useState("");
  const [notBefore, setNotBefore] = useState("");
  const [graceDays, setGraceDays] = useState(30);
  const [notes, setNotes] = useState("");

  const [result, setResult] = useState<IssueLicenseResponse | null>(null);
  const [copied, setCopied] = useState(false);

  // Action modals
  const [selectedLicense, setSelectedLicense] = useState<License | null>(null);
  const [revokeOpen, setRevokeOpen] = useState(false);
  const [revokeReason, setRevokeReason] = useState("");
  const [revokeLoading, setRevokeLoading] = useState(false);
  const [revokeError, setRevokeError] = useState("");

  const [renewOpen, setRenewOpen] = useState(false);
  const [renewExpiresAt, setRenewExpiresAt] = useState("");
  const [renewGraceDays, setRenewGraceDays] = useState(30);
  const [renewLoading, setRenewLoading] = useState(false);
  const [renewError, setRenewError] = useState("");
  const [renewResult, setRenewResult] = useState<RenewLicenseResponse | null>(null);
  const [renewCopied, setRenewCopied] = useState(false);

  const [deleteOpen, setDeleteOpen] = useState(false);
  const [deleteLoading, setDeleteLoading] = useState(false);
  const [deleteError, setDeleteError] = useState("");

  const fetchLicenses = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const data = await api.list<License>("/licenses/");
      setLicenses(data);
    } catch (e: any) {
      setError(e.detail || "加载失败");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchLicenses();
  }, [fetchLicenses]);

  const openModal = async () => {
    setModalOpen(true);
    setModalError("");
    setResult(null);
    setCloudId("");
    setCustomerId("");
    setProductId("");
    setExpiresAt("");
    setNotBefore("");
    setGraceDays(30);
    setNotes("");
    try {
      const [c, p] = await Promise.all([
        api.list<Customer>("/customers/"),
        api.list<Product>("/products/"),
      ]);
      setCustomers(c);
      setProducts(p);
    } catch (e: any) {
      setModalError(e.detail || "加载选项失败");
    }
  };

  const handleIssue = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!cloudId || !customerId || !productId || !expiresAt) {
      setModalError("请填写必填字段");
      return;
    }
    setModalLoading(true);
    setModalError("");
    try {
      const body: IssueLicenseRequest = {
        cloud_id_text: cloudId,
        customer_id: customerId,
        product_id: productId,
        expires_at: new Date(expiresAt).toISOString(),
        grace_seconds: graceDays * 86400,
        notes: notes || undefined,
      };
      if (notBefore) {
        body.not_before = new Date(notBefore).toISOString();
      }
      const res = await api.post<IssueLicenseResponse>("/licenses/", body);
      setResult(res);
      fetchLicenses();
    } catch (err: any) {
      setModalError(err.detail || "签发失败");
    } finally {
      setModalLoading(false);
    }
  };

  const canRenewOrRevoke = (status: string) => {
    return status !== "revoked" && status !== "sunset";
  };

  const openRevoke = (license: License) => {
    setSelectedLicense(license);
    setRevokeReason("");
    setRevokeError("");
    setRevokeOpen(true);
  };

  const handleRevoke = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!revokeReason.trim() || !selectedLicense) return;
    setRevokeLoading(true);
    setRevokeError("");
    try {
      await api.post(`/licenses/${selectedLicense.id}/revoke/`, { reason: revokeReason.trim() });
      setRevokeOpen(false);
      fetchLicenses();
    } catch (err: any) {
      setRevokeError(err.detail || "吊销失败");
    } finally {
      setRevokeLoading(false);
    }
  };

  const openRenew = (license: License) => {
    setSelectedLicense(license);
    const now = new Date();
    now.setFullYear(now.getFullYear() + 1);
    setRenewExpiresAt(now.toISOString().slice(0, 16));
    setRenewGraceDays(30);
    setRenewError("");
    setRenewResult(null);
    setRenewOpen(true);
  };

  const handleRenew = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!renewExpiresAt || !selectedLicense) return;
    setRenewLoading(true);
    setRenewError("");
    try {
      const res = await api.post<RenewLicenseResponse>(`/licenses/${selectedLicense.id}/renew/`, {
        expires_at: new Date(renewExpiresAt).toISOString(),
        grace_seconds: renewGraceDays * 86400,
      });
      setRenewResult(res);
      fetchLicenses();
    } catch (err: any) {
      setRenewError(err.detail || "续期失败");
    } finally {
      setRenewLoading(false);
    }
  };

  const openDelete = (license: License) => {
    setSelectedLicense(license);
    setDeleteError("");
    setDeleteOpen(true);
  };

  const handleDelete = async () => {
    if (!selectedLicense) return;
    setDeleteLoading(true);
    setDeleteError("");
    try {
      await api.delete(`/licenses/${selectedLicense.id}/`);
      setDeleteOpen(false);
      fetchLicenses();
    } catch (err: any) {
      setDeleteError(err.detail || "删除失败");
    } finally {
      setDeleteLoading(false);
    }
  };

  const filtered = licenses.filter((l) => {
    const matchSearch =
      !search ||
      l.license_id.toLowerCase().includes(search.toLowerCase()) ||
      l.customer_name.toLowerCase().includes(search.toLowerCase());
    const matchStatus = !statusFilter || l.status === statusFilter;
    return matchSearch && matchStatus;
  });

  return (
    <div className="p-6 space-y-5">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-bold" style={{ color: "hsl(var(--text-primary))" }}>License</h1>
          <p className="mt-0.5 text-xs font-medium" style={{ color: "hsl(var(--text-secondary))" }}>
            签发、续期、吊销 License 文件
          </p>
        </div>
        <button className="btn-primary" onClick={openModal}>
          <Plus size={16} />
          签发 License
        </button>
      </div>

      {/* Toolbar */}
      <div className="surface flex items-center gap-3 p-3">
        <div className="relative flex-1 max-w-sm">
          <Search size={16} className="absolute left-2.5 top-1/2 -translate-y-1/2" style={{ color: "hsl(var(--text-tertiary))" }} />
          <input
            type="text"
            className="input pl-9"
            placeholder="搜索 License ID / 客户名..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
          />
        </div>
        <div className="flex items-center gap-2">
          <Filter size={16} style={{ color: "hsl(var(--text-tertiary))" }} />
          <select
            className="input w-auto py-1.5 pr-8 text-xs"
            value={statusFilter}
            onChange={(e) => setStatusFilter(e.target.value)}
          >
            <option value="">全部状态</option>
            <option value="active">生效中</option>
            <option value="grace">宽限期</option>
            <option value="expired">已过期</option>
            <option value="revoked">已吊销</option>
            <option value="issued">已签发</option>
            <option value="draft">草稿</option>
          </select>
        </div>
      </div>

      {/* Error */}
      {error && (
        <div className="surface px-4 py-3 text-xs font-medium" style={{ color: "hsl(var(--danger))" }}>
          {error}
        </div>
      )}

      {/* Table */}
      <div className="surface overflow-hidden">
        {loading ? (
          <div className="flex items-center justify-center py-16">
            <Loader2 size={24} className="animate-spin" style={{ color: "hsl(var(--text-tertiary))" }} />
          </div>
        ) : (
          <table className="w-full text-sm">
            <thead>
              <tr style={{ background: "hsl(var(--bg-secondary))" }}>
                <th className="px-4 py-3 text-left text-xs font-semibold" style={{ color: "hsl(var(--text-secondary))" }}>License ID</th>
                <th className="px-4 py-3 text-left text-xs font-semibold" style={{ color: "hsl(var(--text-secondary))" }}>产品</th>
                <th className="px-4 py-3 text-left text-xs font-semibold" style={{ color: "hsl(var(--text-secondary))" }}>客户</th>
                <th className="px-4 py-3 text-left text-xs font-semibold" style={{ color: "hsl(var(--text-secondary))" }}>状态</th>
                <th className="px-4 py-3 text-left text-xs font-semibold" style={{ color: "hsl(var(--text-secondary))" }}>过期时间</th>
                <th className="px-4 py-3 text-left text-xs font-semibold" style={{ color: "hsl(var(--text-secondary))" }}>签名 Key</th>
                <th className="px-4 py-3 text-right text-xs font-semibold" style={{ color: "hsl(var(--text-secondary))" }}>操作</th>
              </tr>
            </thead>
            <tbody>
              {filtered.length === 0 ? (
                <tr>
                  <td colSpan={7} className="px-4 py-16 text-center">
                    <div className="mx-auto mb-3 flex h-12 w-12 items-center justify-center rounded-full" style={{ background: "hsl(var(--bg-tertiary))" }}>
                      <Plus size={20} style={{ color: "hsl(var(--text-tertiary))" }} />
                    </div>
                    <div className="text-sm font-semibold" style={{ color: "hsl(var(--text-secondary))" }}>暂无 License</div>
                    <div className="mt-1 text-xs" style={{ color: "hsl(var(--text-tertiary))" }}>点击右上角「签发 License」开始创建</div>
                  </td>
                </tr>
              ) : (
                filtered.map((l) => {
                  const status = STATUS_MAP[l.status] || { label: l.status, cls: "badge-neutral" };
                  const actionsEnabled = canRenewOrRevoke(l.status);
                  return (
                    <tr key={l.id} className="border-t" style={{ borderColor: "hsl(var(--border))" }}>
                      <td className="px-4 py-3 font-mono text-xs" style={{ color: "hsl(var(--text-primary))" }}>{l.license_id}</td>
                      <td className="px-4 py-3" style={{ color: "hsl(var(--text-secondary))" }}>{l.product_code}</td>
                      <td className="px-4 py-3" style={{ color: "hsl(var(--text-secondary))" }}>{l.customer_name}</td>
                      <td className="px-4 py-3">
                        <span className={`badge ${status.cls}`}>{status.label}</span>
                      </td>
                      <td className="px-4 py-3 text-xs" style={{ color: "hsl(var(--text-secondary))" }}>{formatDate(l.expires_at)}</td>
                      <td className="px-4 py-3 font-mono text-[11px]" style={{ color: "hsl(var(--text-tertiary))" }}>{l.signature_kid}</td>
                      <td className="px-4 py-3 text-right">
                        <div className="flex items-center justify-end gap-1">
                          {actionsEnabled && (
                            <button
                              className="rounded p-1.5 transition-colors hover:bg-gray-100"
                              style={{ color: "hsl(var(--text-secondary))" }}
                              onClick={() => openRenew(l)}
                              title="续期"
                            >
                              <RefreshCw size={14} />
                            </button>
                          )}
                          {actionsEnabled && (
                            <button
                              className="rounded p-1.5 transition-colors hover:bg-gray-100"
                              style={{ color: "hsl(var(--danger))" }}
                              onClick={() => openRevoke(l)}
                              title="吊销"
                            >
                              <Ban size={14} />
                            </button>
                          )}
                          <button
                            className="rounded p-1.5 transition-colors hover:bg-gray-100"
                            style={{ color: "hsl(var(--danger))" }}
                            onClick={() => openDelete(l)}
                            title="删除"
                          >
                            <Trash2 size={14} />
                          </button>
                        </div>
                      </td>
                    </tr>
                  );
                })
              )}
            </tbody>
          </table>
        )}
      </div>

      {/* Issue Modal */}
      <Modal open={modalOpen} onClose={() => setModalOpen(false)} title="签发 License">
        {result ? (
          <div className="space-y-4">
            <div className="rounded-lg px-4 py-3 text-xs font-medium" style={{ background: "hsl(var(--success) / 0.08)", color: "hsl(var(--success))" }}>
              License 签发成功
            </div>
            <div>
              <label className="mb-1.5 block text-xs font-semibold" style={{ color: "hsl(var(--text-secondary))" }}>
                Activation Code
              </label>
              <div className="flex gap-2">
                <input
                  readOnly
                  className="input flex-1 font-mono text-xs"
                  value={result.activation_code}
                />
                <button
                  className="btn-secondary px-3"
                  onClick={() => {
                    navigator.clipboard.writeText(result.activation_code);
                    setCopied(true);
                    setTimeout(() => setCopied(false), 2000);
                  }}
                >
                  {copied ? <Check size={14} /> : <Copy size={14} />}
                </button>
              </div>
            </div>
            <div>
              <label className="mb-1.5 block text-xs font-semibold" style={{ color: "hsl(var(--text-secondary))" }}>
                License ID
              </label>
              <input readOnly className="input font-mono text-xs" value={result.license.license_id} />
            </div>
            <button className="btn-primary w-full" onClick={() => setResult(null)}>
              再签发一个
            </button>
          </div>
        ) : (
          <form onSubmit={handleIssue} className="space-y-4">
            <div>
              <label className="mb-1.5 block text-xs font-semibold" style={{ color: "hsl(var(--text-secondary))" }}>
                Cloud ID <span style={{ color: "hsl(var(--danger))" }}>*</span>
              </label>
              <textarea
                className="input min-h-[80px] text-xs"
                placeholder="粘贴 Cloud ID..."
                value={cloudId}
                onChange={(e) => setCloudId(e.target.value)}
                required
              />
            </div>

            <div className="grid grid-cols-2 gap-3">
              <div>
                <label className="mb-1.5 block text-xs font-semibold" style={{ color: "hsl(var(--text-secondary))" }}>
                  客户 <span style={{ color: "hsl(var(--danger))" }}>*</span>
                </label>
                <select
                  className="input text-xs"
                  value={customerId}
                  onChange={(e) => setCustomerId(e.target.value)}
                  required
                >
                  <option value="">选择客户</option>
                  {customers.map((c) => (
                    <option key={c.id} value={c.id}>{c.display_name}</option>
                  ))}
                </select>
              </div>
              <div>
                <label className="mb-1.5 block text-xs font-semibold" style={{ color: "hsl(var(--text-secondary))" }}>
                  产品 <span style={{ color: "hsl(var(--danger))" }}>*</span>
                </label>
                <select
                  className="input text-xs"
                  value={productId}
                  onChange={(e) => setProductId(e.target.value)}
                  required
                >
                  <option value="">选择产品</option>
                  {products.map((p) => (
                    <option key={p.id} value={p.id}>{p.display_name}</option>
                  ))}
                </select>
              </div>
            </div>

            <div className="grid grid-cols-2 gap-3">
              <div>
                <label className="mb-1.5 block text-xs font-semibold" style={{ color: "hsl(var(--text-secondary))" }}>
                  生效时间
                </label>
                <input
                  type="datetime-local"
                  className="input text-xs"
                  value={notBefore}
                  onChange={(e) => setNotBefore(e.target.value)}
                />
              </div>
              <div>
                <label className="mb-1.5 block text-xs font-semibold" style={{ color: "hsl(var(--text-secondary))" }}>
                  过期时间 <span style={{ color: "hsl(var(--danger))" }}>*</span>
                </label>
                <input
                  type="datetime-local"
                  className="input text-xs"
                  value={expiresAt}
                  onChange={(e) => setExpiresAt(e.target.value)}
                  required
                />
              </div>
            </div>

            <div>
              <label className="mb-1.5 block text-xs font-semibold" style={{ color: "hsl(var(--text-secondary))" }}>
                宽限期（天）
              </label>
              <input
                type="number"
                className="input text-xs"
                min={0}
                value={graceDays}
                onChange={(e) => setGraceDays(Number(e.target.value))}
              />
            </div>

            <div>
              <label className="mb-1.5 block text-xs font-semibold" style={{ color: "hsl(var(--text-secondary))" }}>
                备注
              </label>
              <textarea
                className="input min-h-[60px] text-xs"
                placeholder="可选备注..."
                value={notes}
                onChange={(e) => setNotes(e.target.value)}
              />
            </div>

            {modalError && (
              <div className="rounded-md px-3 py-2 text-xs font-medium" style={{ background: "hsl(var(--danger) / 0.08)", color: "hsl(var(--danger))" }}>
                {modalError}
              </div>
            )}

            <button type="submit" className="btn-primary w-full" disabled={modalLoading}>
              {modalLoading ? <Loader2 size={16} className="animate-spin" /> : "确认签发"}
            </button>
          </form>
        )}
      </Modal>

      {/* Revoke Modal */}
      <Modal open={revokeOpen} onClose={() => setRevokeOpen(false)} title="吊销 License">
        <form onSubmit={handleRevoke} className="space-y-4">
          <div className="flex items-start gap-3 rounded-lg px-4 py-3" style={{ background: "hsl(var(--danger) / 0.08)" }}>
            <AlertTriangle size={18} className="mt-0.5 shrink-0" style={{ color: "hsl(var(--danger))" }} />
            <div className="text-xs" style={{ color: "hsl(var(--danger))" }}>
              <p className="font-semibold">确认吊销 License {selectedLicense?.license_id}?</p>
              <p className="mt-1">吊销后该 License 将立即失效，不可撤销。</p>
            </div>
          </div>
          <div>
            <label className="mb-1.5 block text-xs font-semibold" style={{ color: "hsl(var(--text-secondary))" }}>
              吊销原因 <span style={{ color: "hsl(var(--danger))" }}>*</span>
            </label>
            <textarea
              className="input min-h-[60px] text-xs"
              placeholder="输入吊销原因..."
              value={revokeReason}
              onChange={(e) => setRevokeReason(e.target.value)}
              required
            />
          </div>
          {revokeError && (
            <div className="rounded-md px-3 py-2 text-xs font-medium" style={{ background: "hsl(var(--danger) / 0.08)", color: "hsl(var(--danger))" }}>
              {revokeError}
            </div>
          )}
          <div className="flex gap-3">
            <button type="button" className="btn-secondary flex-1" onClick={() => setRevokeOpen(false)}>
              取消
            </button>
            <button type="submit" className="btn-primary flex-1" disabled={revokeLoading} style={{ background: "hsl(var(--danger))" }}>
              {revokeLoading ? <Loader2 size={16} className="animate-spin" /> : "确认吊销"}
            </button>
          </div>
        </form>
      </Modal>

      {/* Renew Modal */}
      <Modal open={renewOpen} onClose={() => setRenewOpen(false)} title="续期 License">
        {renewResult ? (
          <div className="space-y-4">
            <div className="rounded-lg px-4 py-3 text-xs font-medium" style={{ background: "hsl(var(--success) / 0.08)", color: "hsl(var(--success))" }}>
              License 续期成功
            </div>
            <div>
              <label className="mb-1.5 block text-xs font-semibold" style={{ color: "hsl(var(--text-secondary))" }}>
                新 Activation Code
              </label>
              <div className="flex gap-2">
                <input
                  readOnly
                  className="input flex-1 font-mono text-xs"
                  value={renewResult.activation_code}
                />
                <button
                  className="btn-secondary px-3"
                  onClick={() => {
                    navigator.clipboard.writeText(renewResult.activation_code);
                    setRenewCopied(true);
                    setTimeout(() => setRenewCopied(false), 2000);
                  }}
                >
                  {renewCopied ? <Check size={14} /> : <Copy size={14} />}
                </button>
              </div>
            </div>
            <div>
              <label className="mb-1.5 block text-xs font-semibold" style={{ color: "hsl(var(--text-secondary))" }}>
                新过期时间
              </label>
              <input readOnly className="input text-xs" value={formatDate(renewResult.license.expires_at)} />
            </div>
            <button className="btn-primary w-full" onClick={() => setRenewOpen(false)}>
              关闭
            </button>
          </div>
        ) : (
          <form onSubmit={handleRenew} className="space-y-4">
            <div className="rounded-lg px-4 py-3 text-xs font-medium" style={{ background: "hsl(var(--info) / 0.08)", color: "hsl(var(--info))" }}>
              续期 License {selectedLicense?.license_id}
            </div>
            <div>
              <label className="mb-1.5 block text-xs font-semibold" style={{ color: "hsl(var(--text-secondary))" }}>
                新过期时间 <span style={{ color: "hsl(var(--danger))" }}>*</span>
              </label>
              <input
                type="datetime-local"
                className="input text-xs"
                value={renewExpiresAt}
                onChange={(e) => setRenewExpiresAt(e.target.value)}
                required
              />
            </div>
            <div>
              <label className="mb-1.5 block text-xs font-semibold" style={{ color: "hsl(var(--text-secondary))" }}>
                宽限期（天）
              </label>
              <input
                type="number"
                className="input text-xs"
                min={0}
                value={renewGraceDays}
                onChange={(e) => setRenewGraceDays(Number(e.target.value))}
              />
            </div>
            {renewError && (
              <div className="rounded-md px-3 py-2 text-xs font-medium" style={{ background: "hsl(var(--danger) / 0.08)", color: "hsl(var(--danger))" }}>
                {renewError}
              </div>
            )}
            <button type="submit" className="btn-primary w-full" disabled={renewLoading}>
              {renewLoading ? <Loader2 size={16} className="animate-spin" /> : "确认续期"}
            </button>
          </form>
        )}
      </Modal>

      {/* Delete Confirm Modal */}
      <Modal open={deleteOpen} onClose={() => setDeleteOpen(false)} title="删除 License" width="sm">
        <div className="space-y-4">
          <div className="flex items-start gap-3 rounded-lg px-4 py-3" style={{ background: "hsl(var(--danger) / 0.08)" }}>
            <AlertTriangle size={18} className="mt-0.5 shrink-0" style={{ color: "hsl(var(--danger))" }} />
            <div className="text-xs" style={{ color: "hsl(var(--danger))" }}>
              <p className="font-semibold">确认删除 License {selectedLicense?.license_id}?</p>
              <p className="mt-1">此操作不可撤销，相关记录将从系统中永久移除。</p>
            </div>
          </div>
          {deleteError && (
            <div className="rounded-md px-3 py-2 text-xs font-medium" style={{ background: "hsl(var(--danger) / 0.08)", color: "hsl(var(--danger))" }}>
              {deleteError}
            </div>
          )}
          <div className="flex gap-3">
            <button className="btn-secondary flex-1" onClick={() => setDeleteOpen(false)}>
              取消
            </button>
            <button
              className="btn-primary flex-1"
              disabled={deleteLoading}
              style={{ background: "hsl(var(--danger))" }}
              onClick={handleDelete}
            >
              {deleteLoading ? <Loader2 size={16} className="animate-spin" /> : "确认删除"}
            </button>
          </div>
        </div>
      </Modal>
    </div>
  );
}
