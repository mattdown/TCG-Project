using System;
using System.Collections.Generic;
using Tcg.Protocol;

namespace Tcg.Board
{
    /// <summary>
    /// Something the human decided, sent to the server as one or more act requests. Each step
    /// picks the matching action from the latest state's legal_actions, so indexes never go
    /// stale and the server still decides what's legal.
    /// </summary>
    public interface IGameCommand
    {
        /// <summary>The next action to send, or null when the command is done.</summary>
        GameAction NextAction(GameState state);
    }

    /// <summary>One action: a drop, an inspect button, END TURN.</summary>
    public class ActionCommand : IGameCommand
    {
        readonly GameAction _action;
        bool _sent;

        public ActionCommand(GameAction action) => _action = action;

        public GameAction NextAction(GameState state)
        {
            if (_sent) return null;
            _sent = true;
            return Commands.Find(state, a => a.type == _action.type && a.card == _action.card &&
                                             a.target == _action.target && a.option == _action.option);
        }
    }

    /// <summary>
    /// The mulligan as one decision: the cards to put back are picked (and unpicked) locally,
    /// then sent as a mulligan action each, followed by keep_hand.
    /// </summary>
    public class MulliganCommand : IGameCommand
    {
        readonly Queue<int> _putBack;
        bool _kept;

        public MulliganCommand(IEnumerable<int> putBack) => _putBack = new Queue<int>(putBack);

        public GameAction NextAction(GameState state)
        {
            while (_putBack.Count > 0)
            {
                int uid = _putBack.Dequeue();
                var mark = Commands.Find(state, a => a.type == ActionTypes.Mulligan && a.card == uid);
                if (mark != null) return mark;  // already marked (e.g. a retry after an error): skip it
            }
            if (_kept) return null;
            _kept = true;
            return Commands.Find(state, a => a.type == ActionTypes.KeepHand);
        }
    }

    static class Commands
    {
        public static GameAction Find(GameState state, Predicate<GameAction> match)
        {
            foreach (var a in state.legal_actions)
                if (match(a)) return a;
            return null;
        }
    }
}
