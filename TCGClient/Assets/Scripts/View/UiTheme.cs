using TMPro;
using UnityEngine;

namespace Tcg.View
{
    /// <summary>The shared sprites and fonts, so the editor builder and runtime overlays draw alike.</summary>
    [CreateAssetMenu(menuName = "TCG/UI Theme")]
    public class UiTheme : ScriptableObject
    {
        [Header("Sprites")]
        public Sprite Rounded;      // white rounded rect, 9-sliced, radius 16
        public Sprite Ring;         // white rounded outline, 9-sliced, radius 16, 3 px
        public Sprite RingThin;     // the same outline at 1.5 px: glass panels' rims
        public Sprite Glow;
        public Sprite Dot;
        public Sprite TargetRing;
        public Sprite ArrowHead;
        public Sprite Stripes;
        public Sprite Crown;

        [Header("Fonts")]
        [Tooltip("Marcellus SC: titles, names and button labels.")]
        public TMP_FontAsset Display;
        [Tooltip("Marcellus SC with a soft shadow, for titles over the art.")]
        public Material DisplayShadow;
        [Tooltip("Outfit Medium; <b> is Outfit ExtraBold.")]
        public TMP_FontAsset Body;
        public TMP_FontAsset BodyBold;
        [Tooltip("Outfit ExtraBold: stats, mana, health, floating numbers.")]
        public TMP_FontAsset Numbers;
        [Tooltip("Outfit ExtraBold with a thin dark outline and drop shadow, for numbers on painted art.")]
        public Material NumberOutline;
    }
}
