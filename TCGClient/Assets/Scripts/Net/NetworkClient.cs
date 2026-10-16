using System;
using System.Collections.Concurrent;
using System.Threading;
using NetMQ;
using NetMQ.Sockets;
using Newtonsoft.Json;
using UnityEngine;

/// <summary>
/// The REQ side of the game server's ZeroMQ REQ/REP socket (docs/client-protocol.md).
/// The socket lives on a background thread because REQ/REP blocks and must strictly alternate;
/// requests queue up and each reply is handed back on the main thread, in order.
/// </summary>
public class NetworkClient : MonoBehaviour
{
    public string Address = "tcp://localhost:5555";
    [Tooltip("ai_turn can take a while with the neural opponent.")]
    public float TimeoutSeconds = 30f;

    /// <summary>Raised on the main thread when the server can't be reached or times out.</summary>
    public event Action<string> ConnectionError;

    /// <summary>Requests sent and not yet answered.</summary>
    public int Pending => _pending;

    private readonly ConcurrentQueue<(string json, Action<string> onReply)> _outbox =
        new ConcurrentQueue<(string, Action<string>)>();
    private Thread _thread;
    private volatile bool _running;
    private int _pending;

    void Awake()
    {
        // Created here: the dispatcher's lazy singleton can't be built from the network thread.
        var _ = UnityMainThreadDispatcher.Instance;
        AsyncIO.ForceDotNet.Force();
        _running = true;
        _thread = new Thread(NetworkLoop) { IsBackground = true, Name = "TCG network" };
        _thread.Start();
    }

    /// <summary>Sends a request object as JSON; <paramref name="onReply"/> gets the raw JSON reply.</summary>
    public void Send(object request, Action<string> onReply)
    {
        Interlocked.Increment(ref _pending);
        _outbox.Enqueue((JsonConvert.SerializeObject(request), onReply));
    }

    /// <summary>Sends a request and deserializes the reply as <typeparamref name="T"/>.</summary>
    public void Send<T>(object request, Action<T> onReply)
    {
        Send(request, json => onReply(JsonConvert.DeserializeObject<T>(json)));
    }

    private void NetworkLoop()
    {
        RequestSocket socket = null;
        try
        {
            while (_running)
            {
                if (socket == null)
                {
                    socket = new RequestSocket();
                    socket.Options.Linger = TimeSpan.Zero;
                    socket.Connect(Address);
                }

                if (!_outbox.TryDequeue(out var outgoing))
                {
                    Thread.Sleep(1);
                    continue;
                }

                socket.SendFrame(outgoing.json);
                if (socket.TryReceiveFrameString(TimeSpan.FromSeconds(TimeoutSeconds), out var reply))
                {
                    var onReply = outgoing.onReply;
                    UnityMainThreadDispatcher.Instance.Enqueue(() =>
                    {
                        Interlocked.Decrement(ref _pending);
                        onReply?.Invoke(reply);
                    });
                }
                else
                {
                    // A REQ socket that missed its reply can't send again: drop it and reconnect.
                    socket.Dispose();
                    socket = null;
                    var msg = $"No reply from {Address} after {TimeoutSeconds:0}s. Is the server running? " +
                              "(uv run python -m scripts.server, from PythonServer/)";
                    UnityMainThreadDispatcher.Instance.Enqueue(() =>
                    {
                        Interlocked.Decrement(ref _pending);
                        ConnectionError?.Invoke(msg);
                    });
                }
            }
        }
        catch (Exception e)
        {
            var msg = $"Network error: {e.Message}";
            UnityMainThreadDispatcher.Instance.Enqueue(() => ConnectionError?.Invoke(msg));
        }
        finally
        {
            socket?.Dispose();
            NetMQConfig.Cleanup(false);
        }
    }

    void OnDestroy()
    {
        _running = false;
        // NetMQConfig.Cleanup can hang in Unity (it froze the editor when called here), so it runs
        // on the network thread instead; that's a background thread, so abandoning it is safe.
        if (_thread != null && _thread.IsAlive && !_thread.Join(250))
            Debug.Log("Network thread still shutting down NetMQ; abandoning it.");
    }
}
