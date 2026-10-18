# Diagnóstico Técnico: Pipeline Vulkan Puro, Xwayland e Tela Preta no Motor 3D (League of Legends)

## 1. Visão Geral do Estado Atual

O projeto migrou com sucesso o subsistema de renderização do jogo de **OpenGL/CGL** para **Vulkan Puro** (`CAMetalLayer` -> `VkSurfaceKHR` + `VkSwapchainKHR`).

### O que está funcionando perfeitamente:
1. **Lógica de Jogo, Rede e Simulação**:
   - Conexão com o servidor de jogo estabelecida com sucesso.
   - Carregamento de campeão, mapas e efeitos concluído sem falhas.
   - Transição completa de estados: `PREGAME` -> `SPAWN` -> `GAMESTATE_GAMELOOP`.
   - **Áudio e Entradas**: O som do jogo é reproduzido perfeitamente e o jogo reage ativamente aos cliques do mouse (confirmado pelo usuário na partida).
2. **Crash `SIGABRT` Resolvido**:
   - Anteriormente, o jogo caía com sinal 6 (`SIGABRT`) na marca de 18-19 segundos ao final de `EndRender & EndFrame`.
   - Causa raiz: stubs `-[CAMetalDrawable presentAtTime:]` e `-[CAMetalDrawable presentAfterMinimumDuration:]` em `CAMetalDrawable.mm` chamavam `abort()`.
   - Correção: Redirecionamento de ambos os métodos para `[self present]`. O jogo **não crasha mais** e mantém a simulação ativa.
3. **Ciclo de Vida e Encerramento do Darling (Commit `cf50bc6`)**:
   - Supervisor de ciclo de vida (`tools/riot-lifecycle-supervisor.py`) implementado.
   - Ao fechar o Riot Client sem partida ou League Client em andamento, o `RiotClientServices` e o `darlingserver` são finalizados por completo (zero processos órfãos).
   - Durante partidas ou com a opção "Fechar cliente durante as partidas" ativa, o Darling é preservado para proteger o jogo e a reconexão pós-partida.
4. **AppKit e Janelas (Commits `900c41b` e `98ad7f1`)**:
   - Correção de cliques: removida interceptação de `isMovableByWindowBackground` em `X11Display.m`. Todos os cliques nos botões do launcher, login e League Client funcionam normalmente.
   - Decorações CSD duplicadas removidas via `_MOTIF_WM_HINTS`.

---

## 2. Investigação da Tela Preta: Conclusões Verificadas na Prática

### A. Validação dos Binários em Execução (Ponto 1)
- O executável do jogo (`LeagueofLegends`, localizado em `~/.darling/Applications/League of Legends.app/Contents/LoL/Game/LeagueofLegends.app/Contents/MacOS/LeagueofLegends`) referencia `/System/Library/Frameworks/QuartzCore.framework/Versions/A/QuartzCore` via LC_LOAD_DYLIB.
- O ambiente do launcher (`tools/run-riot-client.sh`) define `DYLD_FRAMEWORK_PATH=/Users/fgeroldi/RuntimeFrameworks`.
- O backend X11 do AppKit (`X11.backend`) reside **exclusivamente** em `/Users/fgeroldi/RuntimeFrameworks/AppKit.framework` (o diretório correspondente em `/System/Library/...` está vazio com 0 bytes), provando que `DYLD_FRAMEWORK_PATH` é respeitado e ativo durante a execução.
- Verificou-se que anteriormente havia uma discrepância temporal e binária entre `~/.darling/System/Library/Frameworks/QuartzCore.framework/Versions/A/QuartzCore` (compilado às 14:57, 258.220 bytes) e `~/.darling/Users/fgeroldi/RuntimeFrameworks/QuartzCore.framework/Versions/A/QuartzCore` (compilado às 15:01, 262.204 bytes).
- O script `tools/build-m58f336-quartzcore.py` agora garante a instalação síncrona de binários idênticos em ambos os locais.

### B. Causa Raiz Confirmada: Falha na Resolução do Display X11 (`nativeDpy`)
- **Por que `getTopLevelWindow` nunca aparecia nos logs anteriores?**
  Na implementação anterior de `CAMetalLayer.mm`:
  ```cpp
  static void* getTopLevelWindow(void* dpy, id subwinObj, void* nativeWin) {
      if (!dpy || !nativeWin) return nativeWin;
  ```
  O ponteiro de display X11 (`nativeDpy`) era obtido exclusivamente via `_CGSNativeDisplay(CGSMainConnectionID())`.
  Em `CoreGraphics/CGS.m`:
  ```objc
  void* _CGSNativeDisplay(CGSConnectionID connId) {
      return [_CGSConnectionForID(connId) nativeDisplay];
  }
  ```
  O backend `CGSConnectionX11` **nunca implementou** `-(void*) nativeDisplay`, e a classe base `CGSConnection` continha apenas um stub abstrato. Além disso, `System/Library/Frameworks/CoreGraphics.framework/.../Backends/X11.backend` não continha binário executável.
  Portanto, `_CGSNativeDisplay(CGSMainConnectionID())` retornava invariavelmente `NULL`.
- **O Loop Infinito resultante**:
  1. Com `nativeDpy == NULL`, a chamada `getTopLevelWindow(nativeDpy, subwinObj, subWin)` atingia `if (!dpy || !nativeWin) return nativeWin;` na primeira linha e retornava `nativeWin` (`0x5200003`) **sem imprimir nenhum log**.
  2. Em `recreateDrawables`, a linha:
     ```cpp
     if (pfn_vkCreateXlibSurfaceKHR && presentationWin && nativeDpy)
     ```
     falhava porque `nativeDpy == NULL`. Todo o bloco de criação de superfície Vulkan (`vkCreateXlibSurfaceKHR`) e swapchain (`vkCreateSwapchainKHR`) era **completamente ignorado**.
  3. `_vkSwapchain` permanecia indefinidamente como `VK_NULL_HANDLE`.
  4. Em `queuePresent:`, ao encontrar `_vkSwapchain == VK_NULL_HANDLE`, o método chamava `recreateDrawables` a cada frame.
  5. O loop de `recreateDrawables subWin=0x5200003 topLevelWin=0x5200003 (presenting on 0x5200003)` se repetia infinitamente, com **zero chamadas Vulkan** e **zero frames apresentados**.
- **A questão do `BadWindow` (Ponto 2)**:
  A hipótese anterior de que `subWin` retornava `BadWindow` era um artefato de ter inspecionado o ID da janela via ferramentas X11 do host após a finalização do processo guest. A subjanela nunca chegou a falhar em nenhuma chamada Vulkan WSI.

---

## 3. Alterações Arquiteturais Implementadas

### 1. Resolução Robusta e Multi-Camadas do Display X11
No `CAMetalLayer.mm`, a resolução de `nativeDpy` foi desacoplada de `_CGSNativeDisplay` e implementada com 5 níveis de fallback:
1. Método `- (void *) nativeDisplay` no objeto de subjanela (`subwinObj`).
2. Ivar `_display` via introspecção em `subwinObj`.
3. Ivar `_display` na janela pai (`parentWindow`).
4. Display ativo do AppKit via `[(X11Display *)[NSDisplay currentDisplay] display]`.
5. Carregamento dinâmico e chamada a `XOpenDisplay(getenv("DISPLAY"))` via `libX11`.

### 2. Exposição de Display e Janelas em `X11SubWindow` e `CGSubWindow`
- Em `CoreGraphics/include/CoreGraphics/CGSubWindow.h` e `CGSubWindow.m`:
  Declarados e implementados `- (void *) parentNativeWindow` e `- (void *) nativeDisplay`.
- Em `AppKit/X11.backend/X11SubWindow.h` e `X11SubWindow.m`:
  Implementados:
  ```objc
  - (void *) nativeDisplay { return (void *) _display; }
  - (Display *) display { return _display; }
  - (Window) window { return _window; }
  ```

### 3. Resolução Robusta de `topLevelWin` Desacoplada de Display
Em `getTopLevelWindow`:
- Início com log obrigatório: `getTopLevelWindow ENTER subWin=%p dpy=%p subwinObj=%p`.
- Resolução via `[subwinObj parentNativeWindow]`, `[subwinObj parentWindow] windowHandle` e ivar `_parent` mesmo se `dpy` for nulo.
- Se `dpy` estiver presente e `XQueryTree` for resolvido via `libX11`, traversal completo da árvore X11 até a raiz (para Xwayland/KWin), registrando cada nível da hierarquia.

### 4. Suporte Empírico a Subjanela e Janela Top-Level na WSI Vulkan (Pontos 3 e 4)
- Controle de alvo via variável `DARLING_VULKAN_PRESENT_TARGET` (`auto` [padrão], `subwin`, `toplevel`).
- No modo `auto`:
  1. Tenta criar `VkSurfaceKHR` e `VkSwapchainKHR` na subjanela `subWin` (WSI DRI3/Present em Xwayland).
  2. Instrumenta detalhadamente:
     - `vkCreateXlibSurfaceKHR` com código de retorno `VkResult`.
     - `vkGetPhysicalDeviceSurfaceSupportKHR` com código de retorno e flag de suporte.
     - `vkGetPhysicalDeviceSurfaceCapabilitiesKHR` registrando extensões mínimas/máximas e limites.
     - `vkCreateSwapchainKHR` com código de retorno, dimensões, formato e modo de apresentação.
  3. Se a subjanela falhar em qualquer etapa, realiza fallback automático para `topLevelWin`.
  4. Ao apresentar na `topLevelWin`, desmapeia (`pfnXUnmapWindow`) a `subWin` opaca para garantir que o conteúdo não seja ocluído pela janela filha preta.
  5. Se bem-sucedido, ativa o swapchain e inicia a apresentação imediata de quadros em `presentDirectVulkan:`.

### 5. Resolução Dinâmica e Verificação de Símbolos do `libX11` (Ponto 5)
Implementada a função `resolveX11Symbols()`, que tenta em ordem:
- `/usr/lib/native/libX11.dylib`
- `libX11.dylib`
- `libX11.so.6`
- `libX11.so`
- `/usr/lib64/libX11.so.6`
Logando o handle retornado e os ponteiros: `XQueryTree`, `XFree`, `XOpenDisplay`, `XMapRaised`, `XMapWindow`, `XUnmapWindow` e `XFlush`.

---

## 4. O Que o Agente Runner Deve Verificar no Próximo Teste

Ao iniciar o jogo através de `tools/run-riot-client.sh` ou `scripts/run.sh`, monitorar `~/.darling/private/tmp/metal-device.log` buscando:

1. **Carregamento da libX11 e símbolos**:
   ```text
   [CAMetalLayer] pid=... dlopen("/usr/lib/native/libX11.dylib") -> ...
   [CAMetalLayer] pid=... libX11 symbols: handle=... XQueryTree=... XOpenDisplay=...
   ```
2. **Resolução de Display e Janela**:
   ```text
   [CAMetalLayer] pid=... recreateDrawables nativeDpy=0x... source=subwinObj.nativeDisplay ...
   [CAMetalLayer] pid=... getTopLevelWindow ENTER subWin=0x... dpy=0x...
   [CAMetalLayer] pid=... getTopLevelWindow: parentNativeWindow resolved topLevelWin=0x...
   ```
3. **Criação da Superfície Vulkan e Swapchain**:
   ```text
   [CAMetalLayer] pid=... Attempting Vulkan WSI on subWin window ...
   [CAMetalLayer] pid=... vkCreateXlibSurfaceKHR res=0 surface=0x... on subWin ...
   [CAMetalLayer] pid=... vkGetPhysicalDeviceSurfaceSupportKHR res=0 supported=1 ...
   [CAMetalLayer] pid=... vkCreateSwapchainKHR res=0 swapchain=0x... extent=...
   [CAMetalLayer] pid=... Swapchain active on subWin ...
   ```
   *(Caso `subWin` retorne erro em Xwayland, observar o fallback imediato para `topLevel` e o unmap da subjanela).*
4. **Apresentação Contínua de Frames**:
   ```text
   [CAMetalLayer] pid=... presentDirectVulkan frame=1 drawable=... acqRes=0 imgIdx=... subRes=0 fenceRes=0 presRes=0
   ```
   Verificar se `presRes == 0` (`VK_SUCCESS`) e se a tela da partida renderiza a imagem do jogo normalmente.
