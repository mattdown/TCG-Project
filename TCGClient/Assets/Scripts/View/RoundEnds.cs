using UnityEngine;
using UnityEngine.EventSystems;
using UnityEngine.UI;

namespace Tcg.View
{
    /// <summary>
    /// Keeps a 9-sliced rounded image's corner radius at half its short side, so pills and round
    /// buttons keep round ends whatever size their layout gives them.
    /// </summary>
    [ExecuteAlways]  // so the scene looks the same in edit mode
    [RequireComponent(typeof(Image))]
    public class RoundEnds : UIBehaviour
    {
        Image _image;

        protected override void OnEnable()
        {
            base.OnEnable();
            Apply();
        }

        protected override void OnRectTransformDimensionsChange() => Apply();

        void Apply()
        {
            if (_image == null) _image = GetComponent<Image>();
            var size = ((RectTransform)transform).rect.size;
            float radius = Mathf.Min(size.x, size.y) / 2f;
            if (radius > 0f) _image.pixelsPerUnitMultiplier = Ui.SliceRadius / radius;
        }
    }
}
