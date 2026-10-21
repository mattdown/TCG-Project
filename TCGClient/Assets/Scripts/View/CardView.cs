using DG.Tweening;
using Tcg.Protocol;
using TMPro;
using UnityEngine;
using UnityEngine.UI;

namespace Tcg.View
{
    public enum CardMark { None, Playable, Selected, Target }

    /// <summary>While a unit's arrow is out: a valid duel target, or the one under the finger.</summary>
    public enum TargetRing { None, Valid, Hovered }

    /// <summary>
    /// The one card design (docs/client-design.md, "The card"): 150x210 at 100%. Shows a card
    /// definition plus its instance state; it never decides anything about the rules.
    /// </summary>
    public class CardView : MonoBehaviour
    {
        public const float Width = 150f, Height = 210f;
        static readonly float[] TextSizes = { 11.5f, 10.5f, 9.5f, 8.5f };
        const float SelectedLift = 10f;
        const float StatsClearance = 50f;  // banner width kept clear of the power and health badges

        [Header("Parts")]
        public RectTransform Visual;
        public Image GlowHalo, GlowRing;
        public Image FrameEdge, BannerFill, Art;
        public GameObject ExhaustedOverlay;
        [Tooltip("Ice over the art: frozen, so it can't attack on its next turn.")]
        public GameObject FrozenOverlay;
        [Tooltip("A veil over the art: Elusive and hasn't attacked, so enemies can't target it.")]
        public GameObject HiddenOverlay;
        public TMP_Text NameText, SubtitleText, BodyText, TraitText, CostText, PowerText, HealthText;
        public Image TargetOutline;
        public CanvasGroup Group;
        [Tooltip("Power and health: hidden on action cards, which have no stats.")]
        public GameObject[] UnitOnly;
        [Tooltip("Shown while the unit has a usable ⟳ ability.")]
        public GameObject AbilityMarker;

        [Header("Art")]
        [Tooltip("Placeholder art: 4 silhouettes per aspect, aspect-major (aspect_1 first).")]
        public Sprite[] ArtSprites;
        public const int ArtPerAspect = 4;

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
            ExhaustedOverlay.SetActive(instance != null && instance.exhausted && !frozen);
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
            Color aspectColour = Palette.Aspect(aspect);
            FrameEdge.color = aspectColour;
            BannerFill.color = aspectColour;
            Art.sprite = PickArt(def, aspect);

            // The name, with the subtitle (the character's version) on a smaller line under it.
            // Units keep the banner's right end clear for the power and health badges over it.
            bool subtitled = !string.IsNullOrEmpty(def.subtitle);
            float right = def.IsAction ? 3f : StatsClearance;
            NameText.text = def.name;
            NameText.rectTransform.offsetMin = new Vector2(NameText.rectTransform.offsetMin.x, subtitled ? 11f : 0f);
            NameText.rectTransform.offsetMax = new Vector2(-right, NameText.rectTransform.offsetMax.y);
            SubtitleText.rectTransform.offsetMax = new Vector2(-right, SubtitleText.rectTransform.offsetMax.y);
            SubtitleText.text = def.subtitle ?? "";
            SubtitleText.gameObject.SetActive(subtitled);
            foreach (var go in UnitOnly) go.SetActive(!def.IsAction);

            // The unit's job, or the card type for action cards.
            TraitText.text = def.traits != null && def.traits.Count > 0
                ? string.Join(" · ", def.traits)
                : TitleCase(def.type);
            SetBodyText(CardText.Build(def, null));
        }

        /// <summary>A subtle marker for a unit with a usable ⟳ ability.</summary>
        public void SetAbilityReady(bool ready)
        {
            if (AbilityMarker != null) AbilityMarker.SetActive(ready);
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
        /// Rich text for the box (keywords and triggers in &lt;b&gt;, flavour in &lt;i&gt;). Shrinks in
        /// four steps so the box never resizes.
        /// </summary>
        public void SetBodyText(string richText)
        {
            BodyText.text = richText;
            BodyText.overflowMode = TextOverflowModes.Ellipsis;  // the full text is in the inspect panel
            var box = BodyText.rectTransform.rect.size;
            foreach (float size in TextSizes)
            {
                BodyText.fontSize = size;
                if (BodyText.GetPreferredValues(richText, box.x, 0f).y <= box.y) break;
            }
        }

        public void SetMark(CardMark mark)
        {
            Mark = mark;
            bool glow = mark != CardMark.None;
            GlowHalo.gameObject.SetActive(glow);
            GlowRing.gameObject.SetActive(glow);
            if (glow)
            {
                Color c = mark == CardMark.Playable ? Palette.GlowPlayable
                    : mark == CardMark.Selected ? Palette.GlowSelected : Palette.GlowTarget;
                GlowRing.color = c;
                GlowHalo.color = c.WithAlpha(mark == CardMark.Selected ? 0.75f : 0.65f);
            }
            Visual.anchoredPosition = new Vector2(0f, mark == CardMark.Selected ? SelectedLift : 0f);
        }

        public void SetDimmed(bool dimmed) => Group.alpha = dimmed ? 0.4f : 1f;

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
            _badge.Find("Face").GetComponent<Image>().color = background;
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
