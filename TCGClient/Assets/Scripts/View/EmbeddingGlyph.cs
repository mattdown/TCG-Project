using System.Collections.Generic;
using UnityEngine;
using UnityEngine.UI;

namespace Tcg.View
{
    /// <summary>
    /// A node's vector as a column of cells, top to bottom: orange for positive values, blue for negative,
    /// fading to navy at zero. Values are read against a shared scale so nodes compare at a glance.
    /// </summary>
    public class EmbeddingGlyph : MaskableGraphic
    {
        public static readonly Color Positive = Palette.Hex("#FB923C");
        public static readonly Color Negative = Palette.Hex("#38BDF8");
        static readonly Color Zero = Palette.Outline;

        IList<float> _values;
        float _scale = 1f;

        public void Set(IList<float> values, float scale)
        {
            _values = values;
            _scale = Mathf.Max(scale, 1e-4f);
            SetVerticesDirty();
        }

        public static Color ColourOf(float value, float scale) =>
            Color.Lerp(Zero, value >= 0f ? Positive : Negative, Mathf.Clamp01(Mathf.Abs(value) / scale));

        protected override void OnPopulateMesh(VertexHelper vh)
        {
            vh.Clear();
            if (_values == null || _values.Count == 0) return;
            var r = rectTransform.rect;
            float cell = r.height / _values.Count;
            float gap = cell > 4f ? 1f : 0f;
            for (int i = 0; i < _values.Count; i++)
            {
                float top = r.yMax - i * cell;
                var colour = ColourOf(_values[i], _scale);
                int start = vh.currentVertCount;
                vh.AddVert(new Vector2(r.xMin, top - cell + gap), colour, Vector2.zero);
                vh.AddVert(new Vector2(r.xMin, top), colour, Vector2.zero);
                vh.AddVert(new Vector2(r.xMax, top), colour, Vector2.zero);
                vh.AddVert(new Vector2(r.xMax, top - cell + gap), colour, Vector2.zero);
                vh.AddTriangle(start, start + 1, start + 2);
                vh.AddTriangle(start + 2, start + 3, start);
            }
        }
    }
}
