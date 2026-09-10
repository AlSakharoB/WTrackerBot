import type { IScannerControls } from "@zxing/browser";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Camera, Flashlight, Keyboard, PackageCheck, Search, TriangleAlert } from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";

import {
  APIError,
  createBarcodeIngredient,
  lookupBarcode,
  type BarcodeIngredientInput,
  type BarcodeLookup,
  type FoodFolder,
  type Ingredient,
} from "../../api/client";
import { BottomSheet, FormField, useToast } from "../ui";
import { stopVideoTracks } from "./camera";

interface BarcodeScannerSheetProps {
  open: boolean;
  initData: string;
  folders: FoodFolder[];
  onClose: () => void;
  onOpenExisting: (ingredient: Ingredient) => void;
}

type ReviewForm = {
  name: string;
  packageWeight: string;
  energy: string;
  protein: string;
  fat: string;
  carbs: string;
  photoUrl: string;
  folderId: string;
};

const EMPTY_FORM: ReviewForm = {
  name: "",
  packageWeight: "",
  energy: "",
  protein: "",
  fat: "",
  carbs: "",
  photoUrl: "",
  folderId: "",
};

const FIELD_LABELS: Record<string, string> = {
  product: "карточка продукта",
  name: "название",
  package_weight_g: "вес упаковки",
  energy_kcal: "калории",
  protein_g: "белки",
  fat_g: "жиры",
  carbs_g: "углеводы",
  photo_url: "фото",
};

function mutationKey(): string {
  return globalThis.crypto?.randomUUID?.() ?? `${Date.now()}-${Math.random()}`;
}

export function BarcodeScannerSheet({
  open,
  initData,
  folders,
  onClose,
  onOpenExisting,
}: BarcodeScannerSheetProps) {
  const queryClient = useQueryClient();
  const { showToast } = useToast();
  const videoRef = useRef<HTMLVideoElement>(null);
  const controlsRef = useRef<IScannerControls | null>(null);
  const lastResultRef = useRef("");
  const scanLockedRef = useRef(false);
  const createKeyRef = useRef(mutationKey());
  const [barcode, setBarcode] = useState("");
  const [cameraActive, setCameraActive] = useState(false);
  const [cameraError, setCameraError] = useState<string | null>(null);
  const [torchAvailable, setTorchAvailable] = useState(false);
  const [torchOn, setTorchOn] = useState(false);
  const [review, setReview] = useState<BarcodeLookup | null>(null);
  const [form, setForm] = useState<ReviewForm>(EMPTY_FORM);
  const [duplicate, setDuplicate] = useState<Ingredient | null>(null);

  const releaseCamera = useCallback(() => {
    controlsRef.current?.stop();
    controlsRef.current = null;
    stopVideoTracks(videoRef.current);
  }, []);

  const stopCamera = useCallback(() => {
    releaseCamera();
    setCameraActive(false);
    setTorchAvailable(false);
    setTorchOn(false);
  }, [releaseCamera]);

  useEffect(() => {
    return releaseCamera;
  }, [releaseCamera]);

  const lookup = useMutation({
    mutationFn: (value: string) => lookupBarcode(initData, value),
    onSuccess: (result) => {
      stopCamera();
      setBarcode(result.barcode);
      setReview(result);
      setDuplicate(null);
      setForm({
        name: result.name ?? "",
        packageWeight: result.package_weight_g ?? "",
        energy: result.nutrition_per_100g.energy_kcal ?? "",
        protein: result.nutrition_per_100g.protein_g ?? "",
        fat: result.nutrition_per_100g.fat_g ?? "",
        carbs: result.nutrition_per_100g.carbs_g ?? "",
        photoUrl: result.photo_url ?? "",
        folderId: "",
      });
      createKeyRef.current = mutationKey();
    },
  });

  const startCamera = async () => {
    setCameraError(null);
    setReview(null);
    lastResultRef.current = "";
    scanLockedRef.current = false;
    if (!navigator.mediaDevices?.getUserMedia) {
      setCameraError("Камера недоступна в этом клиенте. Введите код вручную.");
      return;
    }
    stopCamera();
    try {
      const { BarcodeFormat, BrowserMultiFormatReader } = await import("@zxing/browser");
      const reader = new BrowserMultiFormatReader();
      reader.possibleFormats = [
        BarcodeFormat.EAN_8,
        BarcodeFormat.UPC_A,
        BarcodeFormat.EAN_13,
        BarcodeFormat.ITF,
        BarcodeFormat.CODE_128,
      ];
      const controls = await reader.decodeFromConstraints(
        { video: { facingMode: { ideal: "environment" } }, audio: false },
        videoRef.current ?? undefined,
        (result) => {
          const value = result?.getText();
          if (!value || scanLockedRef.current || value === lastResultRef.current) return;
          scanLockedRef.current = true;
          lastResultRef.current = value;
          setBarcode(value);
          controlsRef.current?.stop();
          stopVideoTracks(videoRef.current);
          lookup.mutate(value);
        },
      );
      controlsRef.current = controls;
      setCameraActive(true);
      setTorchAvailable(Boolean(controls.switchTorch));
    } catch {
      stopCamera();
      setCameraError("Не удалось открыть камеру. Проверьте разрешение или введите код вручную.");
    }
  };

  const toggleTorch = async () => {
    if (!controlsRef.current?.switchTorch) return;
    const next = !torchOn;
    try {
      await controlsRef.current.switchTorch(next);
      setTorchOn(next);
    } catch {
      setTorchAvailable(false);
    }
  };

  const create = useMutation({
    mutationFn: () => {
      const input: BarcodeIngredientInput = {
        confirmation_token: review!.confirmation_token,
        confirmed: true,
        name: form.name,
        energy_kcal_per_100g: form.energy,
        protein_g_per_100g: form.protein,
        fat_g_per_100g: form.fat,
        carbs_g_per_100g: form.carbs,
        package_weight_g: form.packageWeight || null,
        photo_url: form.photoUrl || null,
        folder_id: form.folderId || null,
      };
      return createBarcodeIngredient(initData, review!.barcode, input, createKeyRef.current);
    },
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ["food"] });
      await queryClient.invalidateQueries({ queryKey: ["food-folders"] });
      showToast("Ингредиент создан");
      onClose();
    },
    onError: (error) => {
      if (error instanceof APIError && error.status === 409) {
        const existing = error.details?.existing as Ingredient | undefined;
        if (existing) setDuplicate(existing);
      }
    },
  });

  const close = () => {
    stopCamera();
    onClose();
  };
  const requiredComplete = Boolean(
    form.name.trim() && form.energy && form.protein && form.fat && form.carbs,
  );

  return (
    <BottomSheet open={open} title="Добавить по штрихкоду" onClose={close}>
      <div className="barcode-scanner">
        {!review && (
          <>
            <div className={`scanner-preview ${cameraActive ? "is-active" : ""}`}>
              <video ref={videoRef} playsInline muted aria-label="Изображение с камеры" />
              <div className="scanner-frame" aria-hidden="true" />
              {!cameraActive && <Camera aria-hidden="true" />}
            </div>
            <div className="scanner-actions">
              <button type="button" className="button-secondary button-with-icon" onClick={() => void startCamera()}><Camera aria-hidden="true" size={18} />{cameraActive ? "Перезапустить" : "Включить камеру"}</button>
              {torchAvailable && <button type="button" className={`icon-button ${torchOn ? "is-active" : ""}`} aria-label={torchOn ? "Выключить фонарик" : "Включить фонарик"} title="Фонарик" onClick={() => void toggleTorch()}><Flashlight aria-hidden="true" /></button>}
            </div>
            {cameraError && <p className="scanner-message"><TriangleAlert aria-hidden="true" />{cameraError}</p>}
            <form className="barcode-manual" onSubmit={(event) => { event.preventDefault(); if (barcode.trim()) lookup.mutate(barcode); }}>
              <Keyboard aria-hidden="true" />
              <label className="sr-only" htmlFor="barcode-input">Штрихкод</label>
              <input id="barcode-input" inputMode="numeric" autoComplete="off" value={barcode} onChange={(event) => setBarcode(event.target.value)} placeholder="Введите штрихкод" maxLength={32} />
              <button type="submit" className="icon-button icon-button--primary" aria-label="Найти продукт" title="Найти" disabled={!barcode.trim() || lookup.isPending}><Search aria-hidden="true" /></button>
            </form>
            {lookup.isPending && <p className="scanner-status">Ищем продукт...</p>}
            {lookup.error && <p className="form-error">{lookup.error.message}</p>}
          </>
        )}

        {review && (
          <form className="barcode-review" onSubmit={(event) => { event.preventDefault(); if (requiredComplete) create.mutate(); }}>
            <div className="barcode-product-heading">
              {review.photo_url ? <img src={review.photo_url} alt="Фото продукта из Open Food Facts" /> : <div><PackageCheck aria-hidden="true" /></div>}
              <span><strong>{review.found ? review.name || "Название не указано" : "Продукт не найден"}</strong><small>{review.brand || `Штрихкод ${review.barcode}`}</small><code>{review.barcode}</code></span>
            </div>
            {!review.found && <p className="scanner-message"><TriangleAlert aria-hidden="true" />Заполните данные вручную перед созданием.</p>}
            {(review.missing_fields.length > 0 || review.derived_fields.length > 0) && <div className="barcode-warnings">{review.missing_fields.length > 0 && <p>Нет данных: {review.missing_fields.map((field) => FIELD_LABELS[field] ?? field).join(", ")}.</p>}{review.derived_fields.includes("energy_kcal") && <p>Калории рассчитаны из кДж. Проверьте значение.</p>}</div>}
            <FormField label="Название" htmlFor="barcode-name"><input id="barcode-name" value={form.name} onChange={(event) => setForm({ ...form, name: event.target.value })} /></FormField>
            <FormField label="Папка" htmlFor="barcode-folder"><select id="barcode-folder" value={form.folderId} onChange={(event) => setForm({ ...form, folderId: event.target.value })}><option value="">Без папки</option>{folders.map((folder) => <option key={folder.id} value={folder.id}>{folder.name}</option>)}</select></FormField>
            <FormField label="Вес упаковки, г" htmlFor="barcode-weight" hint={review.package_quantity ? `На упаковке: ${review.package_quantity}` : undefined}><input id="barcode-weight" inputMode="decimal" value={form.packageWeight} onChange={(event) => setForm({ ...form, packageWeight: event.target.value })} /></FormField>
            <fieldset className="nutrition-fields"><legend>КБЖУ на 100 г</legend><FormField label="Ккал" htmlFor="barcode-energy"><input id="barcode-energy" inputMode="decimal" value={form.energy} onChange={(event) => setForm({ ...form, energy: event.target.value })} /></FormField><FormField label="Белки, г" htmlFor="barcode-protein"><input id="barcode-protein" inputMode="decimal" value={form.protein} onChange={(event) => setForm({ ...form, protein: event.target.value })} /></FormField><FormField label="Жиры, г" htmlFor="barcode-fat"><input id="barcode-fat" inputMode="decimal" value={form.fat} onChange={(event) => setForm({ ...form, fat: event.target.value })} /></FormField><FormField label="Углеводы, г" htmlFor="barcode-carbs"><input id="barcode-carbs" inputMode="decimal" value={form.carbs} onChange={(event) => setForm({ ...form, carbs: event.target.value })} /></FormField></fieldset>
            <FormField label="Фото" htmlFor="barcode-photo"><input id="barcode-photo" type="url" value={form.photoUrl} onChange={(event) => setForm({ ...form, photoUrl: event.target.value })} placeholder="https://images.openfoodfacts.org/..." /></FormField>
            <a className="off-attribution" href={review.source_url} target="_blank" rel="noreferrer">Данные Open Food Facts</a>
            {duplicate && <div className="duplicate-notice" role="alert"><div><strong>Продукт уже есть</strong><span>{duplicate.name}</span></div><button type="button" onClick={() => { close(); onOpenExisting(duplicate); }}>Открыть</button></div>}
            {create.error && !duplicate && <p className="form-error">{create.error.message}</p>}
            <div className="sheet-actions"><button type="button" className="button-secondary" onClick={() => { setReview(null); setDuplicate(null); }}>Назад</button><button type="submit" className="button-primary" disabled={!requiredComplete || create.isPending}>{create.isPending ? "Создаем..." : "Создать ингредиент"}</button></div>
          </form>
        )}
      </div>
    </BottomSheet>
  );
}
