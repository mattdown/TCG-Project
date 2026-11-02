using System.Collections.Generic;
using UnityEngine;
using UnityEngine.UI;

namespace Tcg.View
{
    /// <summary>
    /// A node's vector as a column of cells, top to bottom (or a row, left to right, when Horizontal): light for positive values, dark for negative,
    /// mid grey at zero. Greyscale, so the node types' colours stay the loudest thing on screen. Values
    /// are read against a shared scale so nodes compare at a glance.
    /// </summary>
    public class EmbeddingGlyph : MaskableGraphic
    {
        public static readonly Color Positive = Palette.Hex("#F4F5F7");
        public static readonly Color Negative = Palette.Hex("#15181D");
        static readonly Color Zero = Palette.Hex("#6E747D");

        public bool Horizontal;

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
            float cell = (Horizontal ? r.width : r.height) / _values.Count;
            float gap = cell > 4f ? 1f : 0f;
            for (int i = 0; i < _values.Count; i++)
            {
                // Each cell as (x0, y0) to (x1, y1): down the column, or along the row.
                float x0 = Horizontal ? r.xMin + i * cell : r.xMin, x1 = Horizontal ? x0 + cell - gap : r.xMax;
                float y1 = Horizontal ? r.yMax : r.yMax - i * cell, y0 = Horizontal ? r.yMin : y1 - cell + gap;
                var colour = ColourOf(_values[i], _scale);
                int start = vh.currentVertCount;
                vh.AddVert(new Vector2(x0, y0), colour, Vector2.zero);
                vh.AddVert(new Vector2(x0, y1), colour, Vector2.zero);
                vh.AddVert(new Vector2(x1, y1), colour, Vector2.zero);
                vh.AddVert(new Vector2(x1, y0), colour, Vector2.zero);
                vh.AddTriangle(start, start + 1, start + 2);
                vh.AddTriangle(start + 2, start + 3, start);
            }
        }
    }
}
