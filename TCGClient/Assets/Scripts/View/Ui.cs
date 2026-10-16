using TMPro;
using UnityEngine;
using UnityEngine.UI;

namespace Tcg.View
{
    /// <summary>
    /// Small uGUI building blocks in mockup coordinates (CSS px = canvas units at 1280x720, y down
    /// from the parent's top-left). Used by the editor builder and by overlays built at runtime.
    /// </summary>
    public static class Ui
    {
        public const float SliceRadius = 16f;
        public static UiTheme Theme;

        public static RectTransform Node(string name, Transform parent)
        {
            var go = new GameObject(name, typeof(RectTransform)) { layer = 5 };
            var rt = (RectTransform)go.transform;
            rt.SetParent(parent, false);
            return rt;
        }

        /// <summary>A fixed box at (x, y) from the parent's top-left; <paramref name="bottom"/> anchors it
        /// to the bottom edge of the 720 px board instead, so it stays in the corner on taller screens.</summary>
        public static RectTransform Box(string name, Transform parent, float x, float y, float w, float h, bool bottom = false)
        {
            var rt = Node(name, parent);
            rt.anchorMin = rt.anchorMax = new Vector2(0, bottom ? 0 : 1);
            rt.pivot = new Vector2(0, 1);
            rt.anchoredPosition = new Vector2(x, bottom ? 720 - y : -y);
            rt.sizeDelta = new Vector2(w, h);
            return rt;
        }

        public static RectTransform Stretch(string name, Transform parent, float left, float top, float right, float bottom)
        {
            var rt = Node(name, parent);
            rt.anchorMin = Vector2.zero;
            rt.anchorMax = Vector2.one;
            rt.offsetMin = new Vector2(left, bottom);
            rt.offsetMax = new Vector2(-right, -top);
            return rt;
        }

        /// <summary>A strip along the top edge of its parent, <paramref name="height"/> tall.</summary>
        public static RectTransform TopStrip(string name, Transform parent, float inset, float top, float height)
        {
            var rt = Node(name, parent);
            rt.anchorMin = new Vector2(0, 1);
            rt.anchorMax = new Vector2(1, 1);
            rt.offsetMin = new Vector2(inset, -top - height);
            rt.offsetMax = new Vector2(-inset, -top);
            return rt;
        }

        public static void Anchor(RectTransform rt, Vector2 anchor, Vector2 pivot, Vector2 position, Vector2 size)
        {
            rt.anchorMin = rt.anchorMax = anchor;
            rt.pivot = pivot;
            rt.anchoredPosition = position;
            rt.sizeDelta = size;
        }

        public static Image Img(RectTransform rt, Sprite sprite, Color colour)
        {
            var img = rt.gameObject.AddComponent<Image>();
            img.sprite = sprite;
            img.color = colour;
            img.raycastTarget = false;
            return img;
        }

        public static Image Rounded(RectTransform rt, Color colour, float radius) =>
            Sliced(Img(rt, Theme.Rounded, colour), radius);

        /// <summary>A rounded outline; its stroke scales with the radius (3 px at radius 16).</summary>
        public static Image Outline(RectTransform rt, Color colour, float radius) =>
            Sliced(Img(rt, Theme.Ring, colour), radius);

        static Image Sliced(Image img, float radius)
        {
            img.type = Image.Type.Sliced;
            img.pixelsPerUnitMultiplier = SliceRadius / Mathf.Max(radius, 0.5f);
            return img;
        }

        public static TextMeshProUGUI Text(RectTransform rt, string text, TMP_FontAsset font, float size, Color colour,
            TextAlignmentOptions align, Material material = null)
        {
            var t = rt.gameObject.AddComponent<TextMeshProUGUI>();
            t.font = font;
            if (material != null) t.fontSharedMaterial = material;
            t.text = text;
            t.fontSize = size;
            t.color = colour;
            t.alignment = align;
            t.textWrappingMode = TextWrappingModes.NoWrap;
            t.overflowMode = TextOverflowModes.Overflow;
            t.raycastTarget = false;
            t.richText = true;
            return t;
        }

        /// <summary>White Lilita One with the dark outline: numbers, names, button labels.</summary>
        public static TextMeshProUGUI Display(RectTransform rt, string text, float size,
            TextAlignmentOptions align = TextAlignmentOptions.Center) =>
            Text(rt, text, Theme.Lilita, size, Color.white, align, Theme.LilitaOutline);

        public static TextMeshProUGUI Body(RectTransform rt, string text, float size, Color colour,
            TextAlignmentOptions align = TextAlignmentOptions.TopLeft)
        {
            var t = Text(rt, text, Theme.NunitoBlack, size, colour, align);
            t.textWrappingMode = TextWrappingModes.Normal;
            return t;
        }

        /// <summary>A pill label: coloured rounded box with a navy edge that fits its text.</summary>
        public static TextMeshProUGUI Pill(RectTransform rt, string text, Color background, float size = 15f,
            bool display = true)
        {
            Rounded(rt, Palette.Outline, 14);
            var face = Rounded(Stretch("Face", rt, 2, 2, 2, 2), background, 12);
            face.gameObject.AddComponent<LayoutElement>().ignoreLayout = true;
            var layout = rt.gameObject.AddComponent<HorizontalLayoutGroup>();
            layout.padding = new RectOffset(13, 13, 5, 5);
            layout.childControlWidth = layout.childControlHeight = true;
            layout.childForceExpandWidth = layout.childForceExpandHeight = false;
            var fit = rt.gameObject.AddComponent<ContentSizeFitter>();
            fit.horizontalFit = fit.verticalFit = ContentSizeFitter.FitMode.PreferredSize;
            var label = Node("Text", rt);
            return display ? Display(label, text, size) : Text(label, text, Theme.NunitoBlack, size, Color.white,
                TextAlignmentOptions.Center);
        }

        /// <summary>A chunky button: navy edge, darker lip along the bottom, top shine, outlined label.</summary>
        public static Button Button(RectTransform rt, string label, Color face, Color lip, float fontSize,
            out TMP_Text text, float radius = 14f)
        {
            var edge = Rounded(rt, Palette.Outline, radius);
            edge.raycastTarget = true;
            Rounded(Stretch("Lip", rt, 3, 3, 3, 3), lip, radius - 3);
            var faceImg = Rounded(Stretch("Face", rt, 3, 3, 3, 9), face, radius - 3);
            Rounded(TopStrip("Shine", faceImg.rectTransform, 6, 1, 4), Color.white.WithAlpha(0.45f), 2);
            text = Display(Stretch("Label", rt, 8, 3, 8, 9), label, fontSize);
            text.enableAutoSizing = true;
            text.fontSizeMin = 10;
            text.fontSizeMax = fontSize;
            var button = rt.gameObject.AddComponent<Button>();
            button.targetGraphic = edge;
            button.transition = Selectable.Transition.None;
            rt.gameObject.AddComponent<CanvasGroup>();
            rt.gameObject.AddComponent<ButtonDimmer>();
            return button;
        }

        /// <summary>A full-screen tap catcher that dims what's under it.</summary>
        public static Button Scrim(RectTransform parent, string name, float alpha)
        {
            var rt = Stretch(name, parent, 0, 0, 0, 0);
            var img = Img(rt, null, new Color(8 / 255f, 14 / 255f, 32 / 255f, alpha));
            img.raycastTarget = true;
            var b = rt.gameObject.AddComponent<Button>();
            b.transition = Selectable.Transition.None;
            return b;
        }
    }
}
