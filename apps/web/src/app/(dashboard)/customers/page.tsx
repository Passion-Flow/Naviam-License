"use client";

import { useState, useEffect, useCallback } from "react";
import { Plus, Search, Building2, Loader2, Pencil, Trash2, AlertTriangle } from "lucide-react";
import Modal from "@/components/Modal";
import { api, type Customer, type CreateCustomerRequest } from "@/lib/api";

function formatDate(iso: string | null) {
  if (!iso) return "—";
  const d = new Date(iso);
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
}

export default function CustomersPage() {
  const [customers, setCustomers] = useState<Customer[]>([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState("");
  const [error, setError] = useState("");

  const [modalOpen, setModalOpen] = useState(false);
  const [modalLoading, setModalLoading] = useState(false);
  const [modalError, setModalError] = useState("");
  const [editingCustomer, setEditingCustomer] = useState<Customer | null>(null);

  const [displayName, setDisplayName] = useState("");
  const [legalName, setLegalName] = useState("");
  const [contactName, setContactName] = useState("");
  const [contactEmail, setContactEmail] = useState("");
  const [contactPhone, setContactPhone] = useState("");
  const [region, setRegion] = useState("");
  const [notes, setNotes] = useState("");

  const [deleteOpen, setDeleteOpen] = useState(false);
  const [deleteLoading, setDeleteLoading] = useState(false);
  const [deleteError, setDeleteError] = useState("");
  const [deletingCustomer, setDeletingCustomer] = useState<Customer | null>(null);

  const fetchCustomers = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const data = await api.list<Customer>("/customers/");
      setCustomers(data);
    } catch (e: any) {
      setError(e.detail || "加载失败");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchCustomers();
  }, [fetchCustomers]);

  const resetForm = () => {
    setDisplayName("");
    setLegalName("");
    setContactName("");
    setContactEmail("");
    setContactPhone("");
    setRegion("");
    setNotes("");
  };

  const openCreate = () => {
    setEditingCustomer(null);
    setModalError("");
    resetForm();
    setModalOpen(true);
  };

  const openEdit = (customer: Customer) => {
    setEditingCustomer(customer);
    setModalError("");
    setDisplayName(customer.display_name || "");
    setLegalName(customer.legal_name || "");
    setContactName(customer.contact_name || "");
    setContactEmail(customer.contact_email || "");
    setContactPhone(customer.contact_phone || "");
    setRegion(customer.region || "");
    setNotes(customer.notes || "");
    setModalOpen(true);
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!displayName) {
      setModalError("客户名称为必填");
      return;
    }
    setModalLoading(true);
    setModalError("");
    try {
      const body: CreateCustomerRequest = {
        display_name: displayName,
        legal_name: legalName || undefined,
        contact_name: contactName || undefined,
        contact_email: contactEmail || undefined,
        contact_phone: contactPhone || undefined,
        region: region || undefined,
        notes: notes || undefined,
      };
      if (editingCustomer) {
        await api.patch(`/customers/${editingCustomer.id}/`, body);
      } else {
        await api.post<Customer>("/customers/", body);
      }
      setModalOpen(false);
      resetForm();
      fetchCustomers();
    } catch (err: any) {
      setModalError(err.detail || (editingCustomer ? "更新失败" : "创建失败"));
    } finally {
      setModalLoading(false);
    }
  };

  const openDelete = (customer: Customer) => {
    setDeletingCustomer(customer);
    setDeleteError("");
    setDeleteOpen(true);
  };

  const handleDelete = async () => {
    if (!deletingCustomer) return;
    setDeleteLoading(true);
    setDeleteError("");
    try {
      await api.delete(`/customers/${deletingCustomer.id}/`);
      setDeleteOpen(false);
      fetchCustomers();
    } catch (err: any) {
      setDeleteError(err.detail || "删除失败");
    } finally {
      setDeleteLoading(false);
    }
  };

  const filtered = customers.filter((c) =>
    !search ||
    c.display_name.toLowerCase().includes(search.toLowerCase()) ||
    c.contact_name?.toLowerCase().includes(search.toLowerCase())
  );

  return (
    <div className="p-6 space-y-5">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-bold" style={{ color: "hsl(var(--text-primary))" }}>客户</h1>
          <p className="mt-0.5 text-xs font-medium" style={{ color: "hsl(var(--text-secondary))" }}>
            管理客户企业与联系人信息
          </p>
        </div>
        <button className="btn-primary" onClick={openCreate}>
          <Plus size={16} />
          新增客户
        </button>
      </div>

      <div className="surface flex items-center gap-3 p-3">
        <div className="relative flex-1 max-w-sm">
          <Search size={16} className="absolute left-2.5 top-1/2 -translate-y-1/2" style={{ color: "hsl(var(--text-tertiary))" }} />
          <input
            type="text"
            className="input pl-9"
            placeholder="搜索客户名称..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
          />
        </div>
      </div>

      {error && (
        <div className="surface px-4 py-3 text-xs font-medium" style={{ color: "hsl(var(--danger))" }}>
          {error}
        </div>
      )}

      <div className="surface overflow-hidden">
        {loading ? (
          <div className="flex items-center justify-center py-16">
            <Loader2 size={24} className="animate-spin" style={{ color: "hsl(var(--text-tertiary))" }} />
          </div>
        ) : (
          <table className="w-full text-sm">
            <thead>
              <tr style={{ background: "hsl(var(--bg-secondary))" }}>
                <th className="px-4 py-3 text-left text-xs font-semibold" style={{ color: "hsl(var(--text-secondary))" }}>客户名称</th>
                <th className="px-4 py-3 text-left text-xs font-semibold" style={{ color: "hsl(var(--text-secondary))" }}>联系人</th>
                <th className="px-4 py-3 text-left text-xs font-semibold" style={{ color: "hsl(var(--text-secondary))" }}>邮箱</th>
                <th className="px-4 py-3 text-left text-xs font-semibold" style={{ color: "hsl(var(--text-secondary))" }}>地区</th>
                <th className="px-4 py-3 text-left text-xs font-semibold" style={{ color: "hsl(var(--text-secondary))" }}>创建时间</th>
                <th className="px-4 py-3 text-right text-xs font-semibold" style={{ color: "hsl(var(--text-secondary))" }}>操作</th>
              </tr>
            </thead>
            <tbody>
              {filtered.length === 0 ? (
                <tr>
                  <td colSpan={6} className="px-4 py-16 text-center">
                    <div className="mx-auto mb-3 flex h-12 w-12 items-center justify-center rounded-full" style={{ background: "hsl(var(--bg-tertiary))" }}>
                      <Building2 size={20} style={{ color: "hsl(var(--text-tertiary))" }} />
                    </div>
                    <div className="text-sm font-semibold" style={{ color: "hsl(var(--text-secondary))" }}>暂无客户</div>
                    <div className="mt-1 text-xs" style={{ color: "hsl(var(--text-tertiary))" }}>点击「新增客户」创建第一条记录</div>
                  </td>
                </tr>
              ) : (
                filtered.map((c) => (
                  <tr key={c.id} className="border-t" style={{ borderColor: "hsl(var(--border))" }}>
                    <td className="px-4 py-3 font-medium" style={{ color: "hsl(var(--text-primary))" }}>{c.display_name}</td>
                    <td className="px-4 py-3" style={{ color: "hsl(var(--text-secondary))" }}>{c.contact_name || "—"}</td>
                    <td className="px-4 py-3 text-xs" style={{ color: "hsl(var(--text-secondary))" }}>{c.contact_email || "—"}</td>
                    <td className="px-4 py-3 text-xs" style={{ color: "hsl(var(--text-secondary))" }}>{c.region || "—"}</td>
                    <td className="px-4 py-3 text-xs" style={{ color: "hsl(var(--text-tertiary))" }}>{formatDate(c.created_at)}</td>
                    <td className="px-4 py-3 text-right">
                      <div className="flex items-center justify-end gap-1">
                        <button
                          className="rounded p-1.5 transition-colors hover:bg-gray-100"
                          style={{ color: "hsl(var(--text-tertiary))" }}
                          onClick={() => openEdit(c)}
                          title="编辑"
                        >
                          <Pencil size={14} />
                        </button>
                        <button
                          className="rounded p-1.5 transition-colors hover:bg-gray-100"
                          style={{ color: "hsl(var(--danger))" }}
                          onClick={() => openDelete(c)}
                          title="删除"
                        >
                          <Trash2 size={14} />
                        </button>
                      </div>
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        )}
      </div>

      {/* Create/Edit Modal */}
      <Modal open={modalOpen} onClose={() => setModalOpen(false)} title={editingCustomer ? "编辑客户" : "新增客户"}>
        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label className="mb-1.5 block text-xs font-semibold" style={{ color: "hsl(var(--text-secondary))" }}>
              客户名称 <span style={{ color: "hsl(var(--danger))" }}>*</span>
            </label>
            <input
              type="text"
              className="input text-xs"
              placeholder="企业显示名称"
              value={displayName}
              onChange={(e) => setDisplayName(e.target.value)}
              required
            />
          </div>
          <div>
            <label className="mb-1.5 block text-xs font-semibold" style={{ color: "hsl(var(--text-secondary))" }}>
              法定名称
            </label>
            <input
              type="text"
              className="input text-xs"
              placeholder="营业执照上的名称（可选）"
              value={legalName}
              onChange={(e) => setLegalName(e.target.value)}
            />
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="mb-1.5 block text-xs font-semibold" style={{ color: "hsl(var(--text-secondary))" }}>
                联系人
              </label>
              <input
                type="text"
                className="input text-xs"
                value={contactName}
                onChange={(e) => setContactName(e.target.value)}
              />
            </div>
            <div>
              <label className="mb-1.5 block text-xs font-semibold" style={{ color: "hsl(var(--text-secondary))" }}>
                电话
              </label>
              <input
                type="text"
                className="input text-xs"
                value={contactPhone}
                onChange={(e) => setContactPhone(e.target.value)}
              />
            </div>
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="mb-1.5 block text-xs font-semibold" style={{ color: "hsl(var(--text-secondary))" }}>
                邮箱
              </label>
              <input
                type="email"
                className="input text-xs"
                value={contactEmail}
                onChange={(e) => setContactEmail(e.target.value)}
              />
            </div>
            <div>
              <label className="mb-1.5 block text-xs font-semibold" style={{ color: "hsl(var(--text-secondary))" }}>
                地区
              </label>
              <input
                type="text"
                className="input text-xs"
                value={region}
                onChange={(e) => setRegion(e.target.value)}
              />
            </div>
          </div>
          <div>
            <label className="mb-1.5 block text-xs font-semibold" style={{ color: "hsl(var(--text-secondary))" }}>
              备注
            </label>
            <textarea
              className="input min-h-[60px] text-xs"
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
            {modalLoading ? <Loader2 size={16} className="animate-spin" /> : (editingCustomer ? "保存修改" : "创建客户")}
          </button>
        </form>
      </Modal>

      {/* Delete Confirm Modal */}
      <Modal open={deleteOpen} onClose={() => setDeleteOpen(false)} title="删除客户" width="sm">
        <div className="space-y-4">
          <div className="flex items-start gap-3 rounded-lg px-4 py-3" style={{ background: "hsl(var(--danger) / 0.08)" }}>
            <AlertTriangle size={18} className="mt-0.5 shrink-0" style={{ color: "hsl(var(--danger))" }} />
            <div className="text-xs" style={{ color: "hsl(var(--danger))" }}>
              <p className="font-semibold">确认删除客户 {deletingCustomer?.display_name}?</p>
              <p className="mt-1">此操作不可撤销，已关联的 License 记录可能受到影响。</p>
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
