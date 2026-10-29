using UnityEngine;
using UnityEngine.UI;

namespace Tcg.View
{
    /// <summary>
    /// Sizes a background image to cover its parent at any aspect ratio while keeping one line of
    /// the art (the arena's centre line) a fixed distance below the parent's top: the board's
    /// divider, which stays put because the unit rows are anchored to the top.
    /// </summary>
    [ExecuteAlways, RequireComponent(typeof(Image))]
    public class BackgroundFit : MonoBehaviour
    {
        [Tooltip("The art's line, as a fraction of its height down from the top.")]
        public float ArtLine = 0.5f;
        [Tooltip("Where that line goes: canvas units down from the parent's top.")]
        public float BoardLine = 270f;

        Vector2 _fitted;

        void OnEnable() => Fit();

        void Update()
        {
            if (((RectTransform)transform.parent).rect.size != _fitted) Fit();
        }

        void Fit()
        {
            var sprite = GetComponent<Image>().sprite;
            if (sprite == null) return;
            var size = ((RectTransform)transform.parent).rect.size;
            float aspect = sprite.rect.width / sprite.rect.height;
            // Tall enough that the art reaches both the top and the bottom from the pinned line, and wide enough to cover.
            float h = Mathf.Max(BoardLine / ArtLine, (size.y - BoardLine) / (1f - ArtLine), size.x / aspect);
            var rt = (RectTransform)transform;
            rt.anchorMin = rt.anchorMax = new Vector2(0.5f, 1f);
            rt.pivot = new Vector2(0.5f, 1f - ArtLine);
            rt.sizeDelta = new Vector2(h * aspect, h);
            rt.anchoredPosition = new Vector2(0f, -BoardLine);
            _fitted = size;
        }
    }
}
