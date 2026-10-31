using DG.Tweening;
using Tcg.Protocol;
using TMPro;
using UnityEngine;
using UnityEngine.UI;

namespace Tcg.View
{
    public enum CardMark { None, Playable, Selected, Target, Unusable }

    /// <summary>While a unit's arrow is out: a valid duel target, or the one under the finger.</summary>
    public enum TargetRing { None, Valid, Hovered }

    /// <summary>
    /// The one card design (docs/client-design.md, "The card"): 150x210 at 100%. Shows a card
    /// definition plus its instance state; it never decides anything about the rules.
    /// </summary>
    public class CardView : MonoBehaviour
    {
        public const float Width = 150f, Height = 210f;
        const float SelectedLift = 10f;

        [Header("Parts")]
        public RectTransform Visual;
        public Image GlowHalo;
        [Tooltip("The painted frame over the art, and its shadow.")]
        public Image Frame, FrameShadow;
        [Tooltip("The job tag's rim, in the aspect colour.")]
        public Image AspectTag;
        public Image Art;
        [Tooltip("Ice over the art: frozen, so it can't attack on its next turn.")]
        public GameObject FrozenOverlay;
        [Tooltip("A veil over the art: Elusive and hasn't attacked, so enemies can't target it.")]
        public GameObject HiddenOverlay;
        public TMP_Text NameText, SubtitleText, BodyText, TraitText, CostText, PowerText, HealthText;
        public Image TargetOutline;
        [Tooltip("The card's parts, for the help screen's callouts.")]
        public RectTransform CostGem, PowerIcon, HealthIcon, TraitTag;
        public CanvasGroup Group;
        [Tooltip("Power and health: hidden on action cards, which have no stats.")]
        public GameObject[] UnitOnly;

        [Header("Art")]
        [Tooltip("Placeholder art: 4 silhouettes per aspect, aspect-major (aspect_1 first).")]
        public Sprite[] ArtSprites;
        public const int ArtPerAspect = 4;
        const string ArtFolder = "CardArt/";
        const float ArtRaise = 0.1f;  // art taller than the window loses 40% of the overflow at the top, 60% at the bottom
        static readonly System.Collections.Generic.Dictionary<string, Sprite> LoadedArt = new();
        Vector2? _placeholderSize;
        [Tooltip("Units have the power orb and health shield painted on; action cards don't.")]
        public Sprite UnitFrame, ActionFrame;

        public int Uid { get; private set; } = -1;
        public CardDef Def { get; private set; }
        public CardMark Mark { get; private set; }

        public RectTransform Rect => (RectTransform)transform;
        public CardInput Input => _input ? _input : _input = GetComponent<CardInput>();

        CardInput _input;
        RectTransform _badge;
        TMPro.TMP_Text _badgeText;

        /// <summary>Shows <paramref name="def"/> with the state of <paramref name="instance"/> (null: a bare definition).</summary>
        public void Bind(CardDef def, CardInstance instance)
        {
            if (def != Def) BindDefinition(def);
            Def = def;
            Uid = instance?.uid ?? -1;
            bool frozen = instance != null && instance.frozen;
            FrozenOverlay.SetActive(frozen);
            HiddenOverlay.SetActive(instance != null && instance.hidden);

            // Current values from the server, coloured against the printed ones.
            int cost = instance?.cost ?? def.cost;
            CostText.text = cost.ToString();
            CostText.color = Compare(-cost, -def.cost);
            if (def.IsAction) return;
            int power = instance?.power ?? def.power;
            PowerText.text = power.ToString();
            PowerText.color = Compare(power, def.power);
            int health = instance?.health ?? def.health;
            int damage = instance?.damage ?? 0;
            HealthText.text = (health - damage).ToString();
            HealthText.color = damage > 0 ? Palette.StatDown : Compare(health, def.health);
            SetBodyText(CardText.Build(def, instance));
        }

        static Color Compare(int now, int printed) =>
            now > printed ? Palette.StatUp : now < printed ? Palette.StatDown : Color.white;

        void BindDefinition(CardDef def)
        {
            int aspect = Palette.AspectNumber(def.aspects != null && def.aspects.Count > 0 ? def.aspects[0] : null);
            AspectTag.color = Palette.Aspect(aspect);
            ShowArt(def, aspect);
            Frame.sprite = FrameShadow.sprite = def.IsAction ? ActionFrame : UnitFrame;

            // The name on the banner; the subtitle (the character's version) on the tab under it.
            NameText.text = def.name;
            SubtitleText.text = def.subtitle ?? "";
            foreach (var go in UnitOnly) go.SetActive(!def.IsAction);

            // The unit's job, or the card type for action cards.
            TraitText.text = def.traits != null && def.traits.Count > 0
                ? string.Join(" · ", def.traits)
                : TitleCase(def.type);
            SetBodyText(CardText.Build(def, null));
        }

        /// <summary>A quick gold pulse: this card's ability is happening.</summary>
        public Tween Pulse()
        {
            GlowHalo.gameObject.SetActive(true);
            GlowHalo.color = Palette.GlowSelected.WithAlpha(0.8f);
            Visual.DOKill(true);
            return Visual.DOPunchScale(Vector3.one * 0.12f, 0.45f, 6).OnComplete(() => SetMark(Mark));
        }

        /// <summary>
        /// Rich text for the box (keywords and triggers in &lt;b&gt;, flavour in &lt;i&gt;). The prefab
        /// auto-sizes it so the box never resizes.
        /// </summary>
        public void SetBodyText(string richText)
        {
            BodyText.text = richText;
            BodyText.overflowMode = TextOverflowModes.Ellipsis;  // the full text is in the inspect panel
        }

        public void SetMark(CardMark mark)
        {
            Mark = mark;
            bool glow = mark != CardMark.None;
            GlowHalo.gameObject.SetActive(glow);
            if (glow)
            {
                Color c = mark == CardMark.Playable ? Palette.GlowPlayable
                    : mark == CardMark.Selected ? Palette.GlowSelected
                    : mark == CardMark.Unusable ? Palette.GlowUnusable : Palette.GlowTarget;
                GlowHalo.color = c.WithAlpha(mark == CardMark.Selected ? 0.75f : 0.65f);
            }
            Visual.anchoredPosition = new Vector2(0f, mark == CardMark.Selected ? SelectedLift : 0f);
        }

        public void SetDimmed(bool dimmed) => Group.alpha = dimmed ? 0.4f : 1f;

        /// <summary>
        /// Shades the card dark but keeps it opaque, so nothing behind it shows through. It tints
        /// each part's renderer, not its colour, so binding the card again keeps the shade.
        /// </summary>
        public void SetDarkened(bool dark)
        {
            var tint = dark ? new Color(0.38f, 0.38f, 0.38f, 1f) : Color.white;
            foreach (var g in Visual.GetComponentsInChildren<Graphic>(true))
                if (_badge == null || !g.transform.IsChildOf(_badge)) g.canvasRenderer.SetColor(tint);
        }

        public void SetTargetRing(TargetRing ring)
        {
            TargetOutline.gameObject.SetActive(ring != TargetRing.None);
            TargetOutline.color = ring == TargetRing.Hovered ? Palette.GlowTarget : Palette.GlowTarget.WithAlpha(0.75f);
            TargetOutline.pixelsPerUnitMultiplier = Ui.SliceRadius / (ring == TargetRing.Hovered ? 21f : 16f);
            if (ring == TargetRing.Hovered)
            {
                GlowHalo.gameObject.SetActive(true);
                GlowHalo.color = Palette.GlowTarget.WithAlpha(0.7f);
            }
            else
            {
                SetMark(Mark);
            }
        }

        /// <summary>A gold ring: this card can be chosen for the ability waiting on a choice.</summary>
        public void SetChoiceRing(bool on)
        {
            TargetOutline.gameObject.SetActive(on);
            if (!on) return;
            TargetOutline.color = Palette.GlowSelected;
            TargetOutline.pixelsPerUnitMultiplier = Ui.SliceRadius / 21f;
        }

        /// <summary>A pill above the card, e.g. a duel preview ("Defeated"); null hides it.</summary>
        public void SetBadge(string text, Color background)
        {
            if (_badge == null)
            {
                if (string.IsNullOrEmpty(text)) return;
                _badge = Ui.Node("Badge", Visual);
                Ui.Anchor(_badge, new Vector2(0.5f, 1f), new Vector2(0.5f, 0f), new Vector2(0f, 8f), new Vector2(60, 26));
                _badgeText = Ui.Pill(_badge, text, background, 16f);
                _badge.gameObject.AddComponent<CanvasGroup>().ignoreParentGroups = true;  // not dimmed with the card
            }
            _badge.gameObject.SetActive(!string.IsNullOrEmpty(text));
            if (string.IsNullOrEmpty(text)) return;
            _badgeText.text = text;
            Ui.TintPill(_badge, background);
        }

        /// <summary>
        /// The card's generated art (Resources/CardArt/&lt;def.art&gt;) covering the oval window, cropped
        /// more from the bottom than the top so tall caps fit; a placeholder silhouette until it's generated.
        /// </summary>
        void ShowArt(CardDef def, int aspect)
        {
            var art = Art.rectTransform;
            if (_placeholderSize == null) _placeholderSize = art.sizeDelta;
            var sprite = LoadArt(def.art);
            if (sprite == null)
            {
                Art.sprite = PickArt(def, aspect);
                art.sizeDelta = _placeholderSize.Value;
                art.anchoredPosition = Vector2.zero;
                return;
            }
            Art.sprite = sprite;
            var window = ((RectTransform)art.parent).rect.size;
            float aspectRatio = sprite.rect.width / sprite.rect.height;
            var size = window.x / window.y > aspectRatio
                ? new Vector2(window.x, window.x / aspectRatio)
                : new Vector2(window.y * aspectRatio, window.y);
            art.sizeDelta = size;
            art.anchoredPosition = new Vector2(0f, -ArtRaise * (size.y - window.y));
        }

        static Sprite LoadArt(string key)
        {
            if (string.IsNullOrEmpty(key)) return null;
            if (!LoadedArt.TryGetValue(key, out var sprite))
                LoadedArt[key] = sprite = Resources.Load<Sprite>(ArtFolder + key);  // null is cached too
            return sprite;
        }

        Sprite PickArt(CardDef def, int aspect)
        {
            if (ArtSprites == null || ArtSprites.Length == 0) return null;
            // Placeholder art only: a stable silhouette per card, tinted by its aspect.
            int silhouette = (int)(StableHash(def.id) % ArtPerAspect);
            int index = (Mathf.Max(aspect, 1) - 1) * ArtPerAspect + silhouette;
            return ArtSprites[Mathf.Clamp(index, 0, ArtSprites.Length - 1)];
        }

        static uint StableHash(string s)
        {
            uint h = 2166136261;
            foreach (char ch in s ?? "") h = (h ^ ch) * 16777619;
            return h;
        }

        static string TitleCase(string s) =>
            string.IsNullOrEmpty(s) ? "" : char.ToUpperInvariant(s[0]) + s.Substring(1);
    }
}
