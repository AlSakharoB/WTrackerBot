import type { IScannerControls } from "@zxing/browser";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Camera, ExternalLink, Flashlight, ImageOff, Keyboard, PackageCheck, RotateCcw, Search, TriangleAlert } from "lucide-react";
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

function missingHint(review: BarcodeLookup, field: string): string | undefined {
  return review.missing_fields.includes(field) ? "Нет в Open Food Facts, заполните вручную" : undefined;
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
  const openRef = useRef(open);
  const cameraGenerationRef = useRef(0);
  const lastResultRef = useRef("");
  const scanLockedRef = useRef(false);
  const createKeyRef = useRef(mutationKey());
  const createLockedRef = useRef(false);
  const [barcode, setBarcode] = useState("");
  const [cameraActive, setCameraActive] = useState(false);
  const [cameraStarting, setCameraStarting] = useState(false);
  const [cameraError, setCameraError] = useState<string | null>(null);
  const [torchAvailable, setTorchAvailable] = useState(false);
  const [torchOn, setTorchOn] = useState(false);
  const [review, setReview] = useState<BarcodeLookup | null>(null);
  const [manualReview, setManualReview] = useState(false);
  const [confirmed, setConfirmed] = useState(false);
  const [imageFailed, setImageFailed] = useState(false);
  const [form, setForm] = useState<ReviewForm>(EMPTY_FORM);
  const [duplicate, setDuplicate] = useState<Ingredient | null>(null);

  const releaseCamera = useCallback(() => {
    cameraGenerationRef.current += 1;
    controlsRef.current?.stop();
    controlsRef.current = null;
    stopVideoTracks(videoRef.current);
  }, []);

  const stopCamera = useCallback(() => {
    releaseCamera();
    setCameraActive(false);
    setCameraStarting(false);
    setTorchAvailable(false);
    setTorchOn(false);
  }, [releaseCamera]);

  useEffect(() => {
    openRef.current = open;
    if (!open) releaseCamera();
    return () => {
      openRef.current = false;
      releaseCamera();
    };
  }, [open, releaseCamera]);

  useEffect(() => {
    const handleVisibility = () => {
      if (document.visibilityState === "hidden") stopCamera();
    };
    document.addEventListener("visibilitychange", handleVisibility);
    return () => document.removeEventListener("visibilitychange", handleVisibility);
  }, [stopCamera]);

  const lookup = useMutation({
    mutationFn: (value: string) => lookupBarcode(initData, value),
    onSuccess: (result) => {
      if (!openRef.current) return;
      stopCamera();
      setBarcode(result.barcode);
      setReview(result);
      setManualReview(false);
      setConfirmed(false);
      setImageFailed(false);
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
      createLockedRef.current = false;
    },
  });

  const startCamera = async () => {
    setCameraError(null);
    setReview(null);
    setManualReview(false);
    lastResultRef.current = "";
    scanLockedRef.current = false;
    if (!navigator.mediaDevices?.getUserMedia) {
      setCameraError("Камера недоступна в этом клиенте. Введите код вручную.");
      return;
    }
    stopCamera();
    const requestGeneration = cameraGenerationRef.current;
    setCameraStarting(true);
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
          stopCamera();
          lookup.mutate(value);
        },
      );
      if (!openRef.current || requestGeneration !== cameraGenerationRef.current || scanLockedRef.current) {
        controls.stop();
        stopVideoTracks(videoRef.current);
        return;
      }
      controlsRef.current = controls;
      setCameraStarting(false);
      setCameraActive(true);
      setTorchAvailable(Boolean(controls.switchTorch));
    } catch {
      if (openRef.current && requestGeneration === cameraGenerationRef.current) {
        stopCamera();
        setCameraError("Не удалось открыть камеру. Проверьте разрешение или введите код вручную.");
      }
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

  const resetResult = () => {
    setReview(null);
    setManualReview(false);
    setConfirmed(false);
    setImageFailed(false);
    setDuplicate(null);
    lookup.reset();
  };
  const close = () => {
    if (createLockedRef.current) return;
    openRef.current = false;
    stopCamera();
    setBarcode("");
    setReview(null);
    setManualReview(false);
    setConfirmed(false);
    setImageFailed(false);
    setForm(EMPTY_FORM);
    setDuplicate(null);
    lookup.reset();
    onClose();
  };

  const create = useMutation({
    mutationFn: () => {
      const input: BarcodeIngredientInput = {
        confirmation_token: review!.confirmation_token,
        confirmed: true,
        name: form.name.trim(),
        energy_kcal_per_100g: form.energy,
        protein_g_per_100g: form.protein,
        fat_g_per_100g: form.fat,
        carbs_g_per_100g: form.carbs,
        package_weight_g: form.packageWeight.trim() || null,
        photo_url: form.photoUrl.trim() || null,
        folder_id: form.folderId || null,
      };
      return createBarcodeIngredient(initData, review!.barcode, input, createKeyRef.current);
    },
    onSuccess: async () => {
      createLockedRef.current = false;
      await queryClient.invalidateQueries({ queryKey: ["food"] });
      await queryClient.invalidateQueries({ queryKey: ["food-folders"] });
      showToast("Ингредиент создан");
      close();
    },
    onError: (error) => {
      createLockedRef.current = false;
      if (error instanceof APIError && error.status === 409) {
        const existing = error.details?.existing as Ingredient | undefined;
        if (existing) setDuplicate(existing);
      }
    },
  });

  const requiredComplete = Boolean(form.name.trim() && form.energy && form.protein && form.fat && form.carbs);
  const isExternalError = lookup.error instanceof APIError && lookup.error.status >= 500;
  const showReview = Boolean(review && (review.found || manualReview));
  const updateForm = <K extends keyof ReviewForm>(key: K, value: ReviewForm[K]) => {
    setForm((current) => ({ ...current, [key]: value }));
    setDuplicate(null);
    setConfirmed(false);
    createKeyRef.current = mutationKey();
  };

  return (
    <BottomSheet open={open} title="Добавить по штрихкоду" onClose={close}>
      <div className="barcode-scanner">
        {!review && (
          <>
            <div className={`scanner-preview ${cameraActive ? "is-active" : ""}`}>
              <video ref={videoRef} playsInline muted aria-label="Изображение с камеры" />
              <div className="scanner-frame" aria-hidden="true" />
              {!cameraActive && <Camera aria-hidden="true" />}
              {cameraStarting && <span role="status">Открываем камеру...</span>}
            </div>
            <div className="scanner-actions">
              <button type="button" className="button-secondary button-with-icon" onClick={() => void startCamera()} disabled={cameraStarting || lookup.isPending}><Camera aria-hidden="true" size={18} />{cameraStarting ? "Открываем..." : cameraActive ? "Перезапустить" : "Включить камеру"}</button>
              {torchAvailable && <button type="button" className={`icon-button ${torchOn ? "is-active" : ""}`} aria-label={torchOn ? "Выключить фонарик" : "Включить фонарик"} title="Фонарик" onClick={() => void toggleTorch()}><Flashlight aria-hidden="true" /></button>}
            </div>
            {cameraError && <p className="scanner-message" role="alert"><TriangleAlert aria-hidden="true" />{cameraError}</p>}
            <form className="barcode-manual" onSubmit={(event) => { event.preventDefault(); if (barcode.trim() && !lookup.isPending) lookup.mutate(barcode.trim()); }}>
              <Keyboard aria-hidden="true" />
              <label className="sr-only" htmlFor="barcode-input">Штрихкод</label>
              <input id="barcode-input" inputMode="numeric" autoComplete="off" value={barcode} onChange={(event) => setBarcode(event.target.value)} placeholder="Введите штрихкод" maxLength={32} />
              <button type="submit" className="icon-button icon-button--primary" aria-label="Найти продукт" title="Найти" disabled={!barcode.trim() || lookup.isPending}><Search aria-hidden="true" /></button>
            </form>
            {lookup.isPending && <p className="scanner-status" role="status">Ищем продукт...</p>}
            {lookup.error && <div className={`barcode-lookup-error ${isExternalError ? "is-external" : ""}`} role="alert"><TriangleAlert aria-hidden="true" /><div><strong>{isExternalError ? "Open Food Facts временно недоступен" : "Не удалось проверить код"}</strong><span>{lookup.error.message}</span></div><button type="button" className="button-secondary" onClick={() => lookup.mutate(barcode.trim())}>Повторить</button></div>}
          </>
        )}

        {review && !review.found && !manualReview && (
          <section className="barcode-not-found" aria-labelledby="barcode-not-found-title">
            <PackageCheck aria-hidden="true" />
            <h3 id="barcode-not-found-title">В Open Food Facts продукт не найден</h3>
            <code>{review.barcode}</code>
            <p>Можно создать ингредиент вручную и сохранить этот штрихкод в своей базе.</p>
            <button type="button" className="button-primary" onClick={() => setManualReview(true)}>Заполнить вручную</button>
            <button type="button" className="button-secondary button-with-icon" onClick={resetResult}><RotateCcw aria-hidden="true" size={18} />Сканировать снова</button>
          </section>
        )}

        {review && showReview && (
          <form className="barcode-review" onSubmit={(event) => { event.preventDefault(); if (requiredComplete && confirmed && !createLockedRef.current) { createLockedRef.current = true; create.mutate(); } }}>
            <div className="barcode-review-status"><span className={review.derived_fields.length ? "is-derived" : review.missing_fields.length ? "is-incomplete" : "is-complete"}>{review.derived_fields.length ? "Есть расчётные данные" : review.missing_fields.length ? "Неполные данные" : "Данные найдены"}</span><small>Проверьте перед сохранением</small></div>
            <div className="barcode-product-heading">
              {review.photo_url && !imageFailed ? <a href={review.photo_url} target="_blank" rel="noreferrer" aria-label="Открыть фото продукта"><img src={review.photo_url} alt="Фото продукта из Open Food Facts" onError={() => setImageFailed(true)} /></a> : <div className="barcode-photo-fallback"><ImageOff aria-hidden="true" /><span>Фото недоступно</span></div>}
              <span><strong>{review.name || "Название не указано"}</strong><small>{review.brand || "Бренд не указан"}</small>{review.package_quantity && <small>Упаковка: {review.package_quantity}</small>}<code>{review.barcode}</code></span>
            </div>
            {(review.missing_fields.length > 0 || review.derived_fields.length > 0) && <div className="barcode-warnings">{review.missing_fields.length > 0 && <p><TriangleAlert aria-hidden="true" />Нет данных: {review.missing_fields.map((field) => FIELD_LABELS[field] ?? field).join(", ")}.</p>}{review.derived_fields.includes("energy_kcal") && <p id="barcode-derived-energy"><TriangleAlert aria-hidden="true" />Ккал рассчитаны из кДж по формуле: кДж ÷ 4,184. Проверьте значение.</p>}</div>}
            <div className="barcode-form-grid">
              <FormField label="Название" htmlFor="barcode-name" hint={missingHint(review, "name")}><input id="barcode-name" value={form.name} onChange={(event) => updateForm("name", event.target.value)} maxLength={255} /></FormField>
              <FormField label="Папка" htmlFor="barcode-folder"><select id="barcode-folder" value={form.folderId} onChange={(event) => updateForm("folderId", event.target.value)}><option value="">Без папки</option>{folders.map((folder) => <option key={folder.id} value={folder.id}>{folder.name}</option>)}</select></FormField>
              <FormField label="Вес упаковки, г" htmlFor="barcode-weight" hint={review.package_quantity ? `На упаковке: ${review.package_quantity}` : missingHint(review, "package_weight_g")}><input id="barcode-weight" inputMode="decimal" value={form.packageWeight} onChange={(event) => updateForm("packageWeight", event.target.value)} /></FormField>
            </div>
            <fieldset className="nutrition-fields"><legend>КБЖУ на 100 г</legend><FormField label="Ккал" htmlFor="barcode-energy" hint={missingHint(review, "energy_kcal")}><input id="barcode-energy" inputMode="decimal" value={form.energy} aria-describedby={review.derived_fields.includes("energy_kcal") ? "barcode-derived-energy" : undefined} onChange={(event) => updateForm("energy", event.target.value)} /></FormField><FormField label="Белки, г" htmlFor="barcode-protein" hint={missingHint(review, "protein_g")}><input id="barcode-protein" inputMode="decimal" value={form.protein} onChange={(event) => updateForm("protein", event.target.value)} /></FormField><FormField label="Жиры, г" htmlFor="barcode-fat" hint={missingHint(review, "fat_g")}><input id="barcode-fat" inputMode="decimal" value={form.fat} onChange={(event) => updateForm("fat", event.target.value)} /></FormField><FormField label="Углеводы, г" htmlFor="barcode-carbs" hint={missingHint(review, "carbs_g")}><input id="barcode-carbs" inputMode="decimal" value={form.carbs} onChange={(event) => updateForm("carbs", event.target.value)} /></FormField></fieldset>
            <details className="food-editor-details"><summary>Фото и источник</summary><div className="barcode-source-fields"><FormField label="Фото" htmlFor="barcode-photo" hint={missingHint(review, "photo_url")}><input id="barcode-photo" type="url" value={form.photoUrl} onChange={(event) => updateForm("photoUrl", event.target.value)} placeholder="https://images.openfoodfacts.org/..." /></FormField><a className="off-attribution button-with-icon" href={review.source_url} target="_blank" rel="noreferrer"><ExternalLink aria-hidden="true" />Карточка в Open Food Facts</a></div></details>
            <label className="barcode-confirmation"><input type="checkbox" checked={confirmed} onChange={(event) => setConfirmed(event.target.checked)} /><span>Я проверил название, вес упаковки и КБЖУ на 100 г</span></label>
            {duplicate && <div className="duplicate-notice" role="alert"><div><strong>Продукт уже есть в вашей базе</strong><span>{duplicate.name}</span></div><div className="duplicate-notice__actions"><button type="button" onClick={() => { close(); onOpenExisting(duplicate); }}>Открыть</button><button type="button" onClick={() => { setDuplicate(null); setConfirmed(false); }}>Изменить данные</button></div></div>}
            {create.error && !duplicate && <p className="form-error" role="alert">{create.error.message}</p>}
            <div className="sheet-actions"><button type="button" className="button-secondary" onClick={resetResult}>Назад</button><button type="submit" className="button-primary" disabled={!requiredComplete || !confirmed || create.isPending}>{create.isPending ? "Создаем..." : "Создать ингредиент"}</button></div>
          </form>
        )}
      </div>
    </BottomSheet>
  );
}
