using UnityEngine;
using UnityEngine.UI;

namespace Tcg.View
{
    /// <summary>Fades a whole layered button when it isn't interactable (a tint on one layer looks broken).</summary>
    [RequireComponent(typeof(Button), typeof(CanvasGroup))]
    public class ButtonDimmer : MonoBehaviour
    {
        [Range(0f, 1f)] public float DisabledAlpha = 0.55f;
        Button _button;
        CanvasGroup _group;

        void Awake()
        {
            _button = GetComponent<Button>();
            _group = GetComponent<CanvasGroup>();
        }

        void LateUpdate() => _group.alpha = _button.IsInteractable() ? 1f : DisabledAlpha;
    }
}
