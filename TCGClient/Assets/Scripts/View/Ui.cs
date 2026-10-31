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
            if (radius >= Round) img.gameObject.AddComponent<RoundEnds>();
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

        /// <summary>A title or label in Marcellus SC with a soft shadow, in the lantern's pale light.</summary>
        public static TextMeshProUGUI Display(RectTransform rt, string text, float size,
            TextAlignmentOptions align = TextAlignmentOptions.Center) =>
            Text(rt, text, Theme.Display, size, Palette.LanternText, align, Theme.DisplayShadow);

        /// <summary>A white number in Outfit ExtraBold with a thin dark outline: stats, mana, damage.</summary>
        public static TextMeshProUGUI Number(RectTransform rt, string text, float size,
            TextAlignmentOptions align = TextAlignmentOptions.Center) =>
            Text(rt, text, Theme.Numbers, size, Color.white, align, Theme.NumberOutline);

        public static TextMeshProUGUI Body(RectTransform rt, string text, float size, Color colour,
            TextAlignmentOptions align = TextAlignmentOptions.TopLeft)
        {
            var t = Text(rt, text, Theme.Body, size, colour, align);
            t.textWrappingMode = TextWrappingModes.Normal;
            return t;
        }

        /// <summary>A thin rounded outline (1.5 px at radius 16): the rim of glass panels and buttons.</summary>
        public static Image Rim(RectTransform rt, Color colour, float radius) =>
            Sliced(Img(rt, Theme.RingThin, colour), radius);

        /// <summary>
        /// Smoked glass: a dark translucent fill with a thin pale rim. Returns the fill, which is
        /// <paramref name="rt"/>'s own image; the rim is a child that layout groups ignore.
        /// </summary>
        public static Image Panel(RectTransform rt, float radius = 12f, Color? rim = null, float alpha = 0.8f)
        {
            var fill = Rounded(rt, Palette.Glass.WithAlpha(alpha), radius);
            Ignored(Rim(Stretch("Rim", rt, 0, 0, 0, 0), rim ?? Palette.GlassRim, radius));
            return fill;
        }

        /// <summary>
        /// A glass pill that fits its text, washed and rimmed in <paramref name="tint"/>
        /// (<see cref="Palette.Glass"/> for a plain one). <see cref="TintPill"/> recolours it.
        /// </summary>
        public static TextMeshProUGUI Pill(RectTransform rt, string text, Color tint, float size = 15f,
            bool display = true)
        {
            Rounded(rt, Palette.Glass.WithAlpha(0.82f), Round);
            Ignored(Rounded(Stretch("Wash", rt, 0, 0, 0, 0), Color.clear, Round));
            Ignored(Rim(Stretch("Rim", rt, 0, 0, 0, 0), Color.clear, Round));
            var layout = rt.gameObject.AddComponent<HorizontalLayoutGroup>();
            layout.padding = new RectOffset(14, 14, 5, 6);
            layout.childControlWidth = layout.childControlHeight = true;
            layout.childForceExpandWidth = layout.childForceExpandHeight = false;
            var fit = rt.gameObject.AddComponent<ContentSizeFitter>();
            fit.horizontalFit = fit.verticalFit = ContentSizeFitter.FitMode.PreferredSize;
            var label = Node("Text", rt);
            var t = display ? Display(label, text, size) : Text(label, text, Theme.BodyBold, size, Palette.LanternText,
                TextAlignmentOptions.Center);
            TintPill(rt, tint);
            return t;
        }

        public static void TintPill(RectTransform pill, Color tint)
        {
            bool plain = tint == Palette.Glass;
            pill.Find("Wash").GetComponent<Image>().color = plain ? Color.clear : tint.WithAlpha(0.12f);
            pill.Find("Rim").GetComponent<Image>().color = plain ? Palette.GlassRim : tint.WithAlpha(0.9f);
        }

        /// <summary>
        /// A glass button in <paramref name="accent"/>: a wash and rim of it over smoked glass, stronger
        /// for <paramref name="primary"/>, and a pressed state (<see cref="ButtonPress"/>). Round ends
        /// unless given a radius. <see cref="TintButton"/> recolours it.
        /// </summary>
        public static Button Button(RectTransform rt, string label, Color accent, float fontSize,
            out TMP_Text text, bool primary = false, float radius = Round)
        {
            var hit = Img(rt, null, Color.clear);
            hit.raycastTarget = true;
            Rounded(Stretch("Fill", rt, 0, 0, 0, 0), Palette.Glass, radius);  // opaque: a glow behind would show through
            Rounded(Stretch("Wash", rt, 0, 0, 0, 0), Color.clear, radius);
            Rim(Stretch("Rim", rt, 0, 0, 0, 0), Color.clear, radius);
            text = Display(Stretch("Label", rt, 10, 2, 10, 3), label, fontSize);
            text.characterSpacing = 8f;
            text.enableAutoSizing = true;
            text.fontSizeMin = 10;
            text.fontSizeMax = fontSize;
            var button = rt.gameObject.AddComponent<Button>();
            button.targetGraphic = hit;
            button.transition = Selectable.Transition.None;
            rt.gameObject.AddComponent<CanvasGroup>();
            rt.gameObject.AddComponent<ButtonDimmer>();
            rt.gameObject.AddComponent<ButtonPress>();
            TintButton(button, accent, primary);
            return button;
        }

        public static void TintButton(Button button, Color accent, bool primary)
        {
            var rt = button.transform;
            // The project renders in linear space, where a translucent wash reads far stronger than in a browser.
            rt.Find("Wash").GetComponent<Image>().color = accent.WithAlpha(primary ? 0.05f : 0.02f);
            rt.Find("Rim").GetComponent<Image>().color = accent.WithAlpha(primary ? 0.95f : 0.55f);
            rt.Find("Label").GetComponent<TMP_Text>().color = Color.Lerp(accent, Color.white, primary ? 0.75f : 0.6f);
        }

        /// <summary>Round ends: the radius follows half the shape's height (<see cref="RoundEnds"/>).</summary>
        public const float Round = 999f;

        static void Ignored(Graphic g) => g.gameObject.AddComponent<LayoutElement>().ignoreLayout = true;

        /// <summary>A full-screen tap catcher that dims what's under it.</summary>
        public static Button Scrim(RectTransform parent, string name, float alpha)
        {
            var rt = Stretch(name, parent, 0, 0, 0, 0);
            var img = Img(rt, null, Palette.Night.WithAlpha(alpha));
            img.raycastTarget = true;
            var b = rt.gameObject.AddComponent<Button>();
            b.transition = Selectable.Transition.None;
            return b;
        }
    }
}
