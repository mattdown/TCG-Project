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

        [Header("Parts")]
        public RectTransform Visual;
        public Image GlowHalo, GlowRing;
        public Image FrameEdge, BannerFill, Art;
        public GameObject ExhaustedOverlay;
        public Image[] Crowns;
        public TMP_Text NameText, BodyText, TraitText, CostText, PowerText, HealthText;
        public Image CostRim;
        public Image TargetOutline;
        public CanvasGroup Group;

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
            bool newCard = def != Def;
            Def = def;
            Uid = instance?.uid ?? -1;
            if (newCard) BindDefinition(def);

            int damage = instance?.damage ?? 0;
            HealthText.text = (def.health - damage).ToString();
            HealthText.color = damage > 0 ? Palette.StatDown : Color.white;
            ExhaustedOverlay.SetActive(instance != null && instance.exhausted);
        }

        void BindDefinition(CardDef def)
        {
            int aspect = Palette.AspectNumber(def.aspects != null && def.aspects.Count > 0 ? def.aspects[0] : null);
            Color aspectColour = Palette.Aspect(aspect);
            FrameEdge.color = aspectColour;
            BannerFill.color = aspectColour;
            Art.sprite = PickArt(def, aspect);

            NameText.text = def.name;
            CostText.text = def.cost.ToString();
            CostRim.color = def.energy_source ? Palette.Gold : Palette.Outline;
            PowerText.text = def.power.ToString();
            PowerText.color = Color.white;
            for (int i = 0; i < Crowns.Length; i++)
                Crowns[i].gameObject.SetActive(i < def.score);

            TraitText.text = def.traits != null && def.traits.Count > 0
                ? string.Join(" · ", def.traits)
                : TitleCase(def.type);
            // The protocol has no ability or flavour text yet, so vanilla cards leave the box empty.
            SetBodyText("");
        }

        /// <summary>
        /// Rich text for the box (keywords and triggers in &lt;b&gt;, flavour in &lt;i&gt;). Shrinks in
        /// four steps so the box never resizes.
        /// </summary>
        public void SetBodyText(string richText)
        {
            BodyText.text = richText;
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
