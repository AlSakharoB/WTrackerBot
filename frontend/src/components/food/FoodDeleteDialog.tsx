import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useRef } from "react";

import { deleteFood, fetchDeleteConsequence, type FoodKind } from "../../api/client";
import { ConfirmDialog, useToast } from "../ui";

interface FoodDeleteDialogProps {
  item: { id: string; name: string };
  kind: FoodKind;
  initData: string;
  confirmDeletions: boolean;
  onClose: () => void;
}

export function FoodDeleteDialog({ item, kind, initData, confirmDeletions, onClose }: FoodDeleteDialogProps) {
  const queryClient = useQueryClient();
  const { showToast } = useToast();
  const autoAttempted = useRef(false);
  const submitting = useRef(false);
  const consequence = useQuery({
    queryKey: ["food-delete-consequence", kind, item.id],
    queryFn: () => fetchDeleteConsequence(initData, kind, item.id),
    retry: false,
    staleTime: 0,
  });
  const remove = useMutation({
    mutationFn: () => deleteFood(initData, kind, item.id),
    onSuccess: async () => {
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ["food"] }),
        queryClient.invalidateQueries({ queryKey: ["food-folders"] }),
        queryClient.invalidateQueries({ queryKey: ["ration-sources"] }),
      ]);
      showToast(kind === "ingredients" ? "Ингредиент удалён" : "Блюдо удалено");
      onClose();
    },
    onSettled: () => { submitting.current = false; },
  });
  const { mutate } = remove;
  useEffect(() => {
    if (confirmDeletions || !consequence.data?.can_delete || consequence.isFetching || autoAttempted.current) return;
    autoAttempted.current = true;
    submitting.current = true;
    mutate();
  }, [confirmDeletions, consequence.data, consequence.isFetching, mutate]);
  const blocked = consequence.data?.can_delete === false;
  return <ConfirmDialog
    open={confirmDeletions || blocked || Boolean(consequence.error || remove.error)}
    title={blocked ? "Удаление недоступно" : `Удалить ${kind === "ingredients" ? "ингредиент" : "блюдо"}?`}
    description={remove.error?.message ?? consequence.error?.message ?? (consequence.isFetching ? "Проверяем связанные данные..." : consequence.data?.message ?? item.name)}
    confirmLabel={blocked ? "Понятно" : consequence.error ? "Повторить проверку" : remove.isPending ? "Удаляем..." : "Удалить"}
    confirmDisabled={consequence.isPending || consequence.isFetching || remove.isPending}
    destructive={!blocked && !consequence.error}
    onClose={() => { if (!remove.isPending) onClose(); }}
    onConfirm={() => {
      if (blocked) onClose();
      else if (consequence.error) void consequence.refetch();
      else if (consequence.data?.can_delete && !submitting.current) {
        submitting.current = true;
        remove.mutate();
      }
    }}
  />;
}
