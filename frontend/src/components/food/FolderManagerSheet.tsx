import { useMutation, useQueryClient } from "@tanstack/react-query";
import { ArrowDown, ArrowUp, Check, FolderPlus, Pencil, Trash2, X } from "lucide-react";
import { useRef, useState } from "react";

import {
  createFoodFolder,
  deleteFoodFolder,
  renameFoodFolder,
  reorderFoodFolders,
  type FoodFolder,
} from "../../api/client";
import { BottomSheet, ConfirmDialog, useToast } from "../ui";

interface FolderManagerSheetProps {
  open: boolean;
  initData: string;
  folders: FoodFolder[];
  onClose: () => void;
}

function mutationKey(): string {
  return globalThis.crypto?.randomUUID?.() ?? `${Date.now()}-${Math.random()}`;
}

export function FolderManagerSheet({
  open,
  initData,
  folders,
  onClose,
}: FolderManagerSheetProps) {
  const queryClient = useQueryClient();
  const { showToast } = useToast();
  const [newName, setNewName] = useState("");
  const [editingId, setEditingId] = useState<string | null>(null);
  const [editingName, setEditingName] = useState("");
  const [deleting, setDeleting] = useState<FoodFolder | null>(null);
  const createKey = useRef(mutationKey());

  const refresh = async () => {
    await queryClient.invalidateQueries({ queryKey: ["food-folders"] });
    await queryClient.invalidateQueries({ queryKey: ["food"] });
  };
  const create = useMutation({
    mutationFn: () => createFoodFolder(initData, newName, createKey.current),
    onSuccess: async () => {
      setNewName("");
      createKey.current = mutationKey();
      await refresh();
      showToast("Папка создана");
    },
  });
  const rename = useMutation({
    mutationFn: () => renameFoodFolder(initData, editingId!, editingName),
    onSuccess: async () => {
      setEditingId(null);
      await refresh();
      showToast("Название изменено");
    },
  });
  const remove = useMutation({
    mutationFn: () => deleteFoodFolder(initData, deleting!.id),
    onSuccess: async () => {
      setDeleting(null);
      await refresh();
      showToast("Папка удалена, позиции остались в каталоге");
    },
  });
  const reorder = useMutation({
    mutationFn: (ids: string[]) => reorderFoodFolders(initData, ids),
    onSuccess: refresh,
  });

  const move = (index: number, direction: -1 | 1) => {
    const target = index + direction;
    if (target < 0 || target >= folders.length) return;
    const ids = folders.map((folder) => folder.id);
    [ids[index], ids[target]] = [ids[target], ids[index]];
    reorder.mutate(ids);
  };
  const error = create.error ?? rename.error ?? remove.error ?? reorder.error;

  return (
    <>
      <BottomSheet open={open} title="Папки еды" onClose={onClose}>
        <form
          className="folder-create"
          onSubmit={(event) => {
            event.preventDefault();
            if (newName.trim()) create.mutate();
          }}
        >
          <label className="sr-only" htmlFor="new-folder-name">Название новой папки</label>
          <input id="new-folder-name" value={newName} onChange={(event) => { setNewName(event.target.value); createKey.current = mutationKey(); }} placeholder="Новая папка" maxLength={100} />
          <button type="submit" className="icon-button icon-button--primary" aria-label="Создать папку" title="Создать папку" disabled={!newName.trim() || create.isPending}><FolderPlus aria-hidden="true" /></button>
        </form>

        <div className="folder-manager-list">
          {folders.map((folder, index) => (
            <div className="folder-manager-row" key={folder.id}>
              {editingId === folder.id ? (
                <form onSubmit={(event) => { event.preventDefault(); if (editingName.trim()) rename.mutate(); }}>
                  <label className="sr-only" htmlFor={`folder-${folder.id}`}>Название папки</label>
                  <input id={`folder-${folder.id}`} value={editingName} onChange={(event) => setEditingName(event.target.value)} maxLength={100} autoFocus />
                  <button type="submit" aria-label="Сохранить название" title="Сохранить" disabled={!editingName.trim() || rename.isPending}><Check aria-hidden="true" /></button>
                  <button type="button" aria-label="Отменить переименование" title="Отменить" onClick={() => setEditingId(null)}><X aria-hidden="true" /></button>
                </form>
              ) : (
                <div className="folder-manager-row__name"><strong>{folder.name}</strong><small>{folder.item_count} поз.</small></div>
              )}
              {editingId !== folder.id && (
                <div className="folder-manager-row__actions">
                  <button type="button" aria-label={`Переместить ${folder.name} выше`} title="Выше" disabled={index === 0 || reorder.isPending} onClick={() => move(index, -1)}><ArrowUp aria-hidden="true" /></button>
                  <button type="button" aria-label={`Переместить ${folder.name} ниже`} title="Ниже" disabled={index === folders.length - 1 || reorder.isPending} onClick={() => move(index, 1)}><ArrowDown aria-hidden="true" /></button>
                  <button type="button" aria-label={`Переименовать ${folder.name}`} title="Переименовать" onClick={() => { setEditingId(folder.id); setEditingName(folder.name); }}><Pencil aria-hidden="true" /></button>
                  <button type="button" className="is-danger" aria-label={`Удалить ${folder.name}`} title="Удалить" onClick={() => setDeleting(folder)}><Trash2 aria-hidden="true" /></button>
                </div>
              )}
            </div>
          ))}
          {folders.length === 0 && <p className="folder-empty">Создайте папку, чтобы сгруппировать продукты и блюда.</p>}
        </div>
        {error && <p className="form-error">{error.message}</p>}
      </BottomSheet>
      <ConfirmDialog
        open={deleting !== null}
        title={`Удалить папку «${deleting?.name ?? ""}»?`}
        description={`${deleting?.item_count ?? 0} поз. перейдут в «Без папки». Сами продукты и блюда не удалятся.`}
        confirmLabel="Удалить папку"
        destructive
        onClose={() => setDeleting(null)}
        onConfirm={() => remove.mutate()}
      />
    </>
  );
}
