"use client";

import { useState, useEffect, useCallback } from "react";
import { Plus, Search, Package, Loader2, Pencil, Trash2, AlertTriangle } from "lucide-react";
import Modal from "@/components/Modal";
import { api, type Product, type CreateProductRequest } from "@/lib/api";

function formatDate(iso: string | null) {
  if (!iso) return "—";
  const d = new Date(iso);
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
}

export default function ProductsPage() {
  const [products, setProducts] = useState<Product[]>([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState("");
  const [error, setError] = useState("");

  const [modalOpen, setModalOpen] = useState(false);
  const [modalLoading, setModalLoading] = useState(false);
  const [modalError, setModalError] = useState("");
  const [editingProduct, setEditingProduct] = useState<Product | null>(null);

  const [code, setCode] = useState("");
  const [displayName, setDisplayName] = useState("");
  const [description, setDescription] = useState("");
  const [schemaVersion, setSchemaVersion] = useState(1);

  const [deleteOpen, setDeleteOpen] = useState(false);
  const [deleteLoading, setDeleteLoading] = useState(false);
  const [deleteError, setDeleteError] = useState("");
  const [deletingProduct, setDeletingProduct] = useState<Product | null>(null);

  const fetchProducts = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const data = await api.list<Product>("/products/");
      setProducts(data);
    } catch (e: any) {
      setError(e.detail || "加载失败");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchProducts();
  }, [fetchProducts]);

  const resetForm = () => {
    setCode("");
    setDisplayName("");
    setDescription("");
    setSchemaVersion(1);
  };

  const openCreate = () => {
    setEditingProduct(null);
    setModalError("");
    resetForm();
    setModalOpen(true);
  };

  const openEdit = (product: Product) => {
    setEditingProduct(product);
    setModalError("");
    setCode(product.code || "");
    setDisplayName(product.display_name || "");
    setDescription(product.description || "");
    setSchemaVersion(product.schema_version || 1);
    setModalOpen(true);
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!code || !displayName) {
      setModalError("产品代码和显示名称均为必填");
      return;
    }
    setModalLoading(true);
    setModalError("");
    try {
      const body: CreateProductRequest = {
        code,
        display_name: displayName,
        description: description || undefined,
        schema_version: schemaVersion,
      };
      if (editingProduct) {
        await api.patch(`/products/${editingProduct.id}/`, body);
      } else {
        await api.post<Product>("/products/", body);
      }
      setModalOpen(false);
      resetForm();
      fetchProducts();
    } catch (err: any) {
      setModalError(err.detail || (editingProduct ? "更新失败" : "创建失败"));
    } finally {
      setModalLoading(false);
    }
  };

  const openDelete = (product: Product) => {
    setDeletingProduct(product);
    setDeleteError("");
    setDeleteOpen(true);
  };

  const handleDelete = async () => {
    if (!deletingProduct) return;
    setDeleteLoading(true);
    setDeleteError("");
    try {
      await api.delete(`/products/${deletingProduct.id}/`);
      setDeleteOpen(false);
      fetchProducts();
    } catch (err: any) {
      setDeleteError(err.detail || "删除失败");
    } finally {
      setDeleteLoading(false);
    }
  };

  const filtered = products.filter((p) =>
    !search ||
    p.display_name.toLowerCase().includes(search.toLowerCase()) ||
    p.code.toLowerCase().includes(search.toLowerCase())
  );

  return (
    <div className="p-6 space-y-5">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-bold" style={{ color: "hsl(var(--text-primary))" }}>产品</h1>
          <p className="mt-0.5 text-xs font-medium" style={{ color: "hsl(var(--text-secondary))" }}>
            管理产品与 Cloud ID 协议版本
          </p>
        </div>
        <button className="btn-primary" onClick={openCreate}>
          <Plus size={16} />
          新增产品
        </button>
      </div>

      <div className="surface flex items-center gap-3 p-3">
        <div className="relative flex-1 max-w-sm">
          <Search size={16} className="absolute left-2.5 top-1/2 -translate-y-1/2" style={{ color: "hsl(var(--text-tertiary))" }} />
          <input
            type="text"
            className="input pl-9"
            placeholder="搜索产品名称 / 代码..."
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
                <th className="px-4 py-3 text-left text-xs font-semibold" style={{ color: "hsl(var(--text-secondary))" }}>产品名称</th>
                <th className="px-4 py-3 text-left text-xs font-semibold" style={{ color: "hsl(var(--text-secondary))" }}>代码</th>
                <th className="px-4 py-3 text-left text-xs font-semibold" style={{ color: "hsl(var(--text-secondary))" }}>协议版本</th>
                <th className="px-4 py-3 text-left text-xs font-semibold" style={{ color: "hsl(var(--text-secondary))" }}>描述</th>
                <th className="px-4 py-3 text-left text-xs font-semibold" style={{ color: "hsl(var(--text-secondary))" }}>创建时间</th>
                <th className="px-4 py-3 text-right text-xs font-semibold" style={{ color: "hsl(var(--text-secondary))" }}>操作</th>
              </tr>
            </thead>
            <tbody>
              {filtered.length === 0 ? (
                <tr>
                  <td colSpan={6} className="px-4 py-16 text-center">
                    <div className="mx-auto mb-3 flex h-12 w-12 items-center justify-center rounded-full" style={{ background: "hsl(var(--bg-tertiary))" }}>
                      <Package size={20} style={{ color: "hsl(var(--text-tertiary))" }} />
                    </div>
                    <div className="text-sm font-semibold" style={{ color: "hsl(var(--text-secondary))" }}>暂无产品</div>
                    <div className="mt-1 text-xs" style={{ color: "hsl(var(--text-tertiary))" }}>点击「新增产品」创建第一条记录</div>
                  </td>
                </tr>
              ) : (
                filtered.map((p) => (
                  <tr key={p.id} className="border-t" style={{ borderColor: "hsl(var(--border))" }}>
                    <td className="px-4 py-3 font-medium" style={{ color: "hsl(var(--text-primary))" }}>{p.display_name}</td>
                    <td className="px-4 py-3 font-mono text-xs" style={{ color: "hsl(var(--text-secondary))" }}>{p.code}</td>
                    <td className="px-4 py-3 text-xs" style={{ color: "hsl(var(--text-secondary))" }}>v{p.schema_version}</td>
                    <td className="px-4 py-3 text-xs" style={{ color: "hsl(var(--text-tertiary))" }}>{p.description || "—"}</td>
                    <td className="px-4 py-3 text-xs" style={{ color: "hsl(var(--text-tertiary))" }}>{formatDate(p.created_at)}</td>
                    <td className="px-4 py-3 text-right">
                      <div className="flex items-center justify-end gap-1">
                        <button
                          className="rounded p-1.5 transition-colors hover:bg-gray-100"
                          style={{ color: "hsl(var(--text-tertiary))" }}
                          onClick={() => openEdit(p)}
                          title="编辑"
                        >
                          <Pencil size={14} />
                        </button>
                        <button
                          className="rounded p-1.5 transition-colors hover:bg-gray-100"
                          style={{ color: "hsl(var(--danger))" }}
                          onClick={() => openDelete(p)}
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
      <Modal open={modalOpen} onClose={() => setModalOpen(false)} title={editingProduct ? "编辑产品" : "新增产品"}>
        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label className="mb-1.5 block text-xs font-semibold" style={{ color: "hsl(var(--text-secondary))" }}>
              产品代码 <span style={{ color: "hsl(var(--danger))" }}>*</span>
            </label>
            <input
              type="text"
              className="input text-xs font-mono"
              placeholder="如 default、pro-enterprise"
              value={code}
              onChange={(e) => setCode(e.target.value)}
              required
              disabled={!!editingProduct}
            />
            {editingProduct && (
              <p className="mt-1 text-[11px]" style={{ color: "hsl(var(--text-tertiary))" }}>产品代码不可修改</p>
            )}
          </div>
          <div>
            <label className="mb-1.5 block text-xs font-semibold" style={{ color: "hsl(var(--text-secondary))" }}>
              显示名称 <span style={{ color: "hsl(var(--danger))" }}>*</span>
            </label>
            <input
              type="text"
              className="input text-xs"
              placeholder="产品显示名称"
              value={displayName}
              onChange={(e) => setDisplayName(e.target.value)}
              required
            />
          </div>
          <div>
            <label className="mb-1.5 block text-xs font-semibold" style={{ color: "hsl(var(--text-secondary))" }}>
              协议版本
            </label>
            <input
              type="number"
              className="input text-xs"
              min={1}
              value={schemaVersion}
              onChange={(e) => setSchemaVersion(Number(e.target.value))}
            />
          </div>
          <div>
            <label className="mb-1.5 block text-xs font-semibold" style={{ color: "hsl(var(--text-secondary))" }}>
              描述
            </label>
            <textarea
              className="input min-h-[60px] text-xs"
              placeholder="产品描述（可选）"
              value={description}
              onChange={(e) => setDescription(e.target.value)}
            />
          </div>

          {modalError && (
            <div className="rounded-md px-3 py-2 text-xs font-medium" style={{ background: "hsl(var(--danger) / 0.08)", color: "hsl(var(--danger))" }}>
              {modalError}
            </div>
          )}

          <button type="submit" className="btn-primary w-full" disabled={modalLoading}>
            {modalLoading ? <Loader2 size={16} className="animate-spin" /> : (editingProduct ? "保存修改" : "创建产品")}
          </button>
        </form>
      </Modal>

      {/* Delete Confirm Modal */}
      <Modal open={deleteOpen} onClose={() => setDeleteOpen(false)} title="删除产品" width="sm">
        <div className="space-y-4">
          <div className="flex items-start gap-3 rounded-lg px-4 py-3" style={{ background: "hsl(var(--danger) / 0.08)" }}>
            <AlertTriangle size={18} className="mt-0.5 shrink-0" style={{ color: "hsl(var(--danger))" }} />
            <div className="text-xs" style={{ color: "hsl(var(--danger))" }}>
              <p className="font-semibold">确认删除产品 {deletingProduct?.display_name}?</p>
              <p className="mt-1">此操作不可撤销，已关联的 License 可能受到影响。</p>
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
