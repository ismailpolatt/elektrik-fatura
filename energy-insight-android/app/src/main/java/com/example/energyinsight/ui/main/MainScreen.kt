package com.example.energyinsight.ui.main

import android.content.Context
import android.net.Uri
import android.webkit.ValueCallback
import android.webkit.WebChromeClient
import android.webkit.WebView
import android.webkit.WebViewClient
import androidx.compose.foundation.layout.*
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.unit.dp
import androidx.compose.ui.viewinterop.AndroidView
import androidx.navigation3.runtime.NavKey
import com.example.energyinsight.MainActivity

@Composable
fun MainScreen(
  onItemClick: (NavKey) -> Unit = {},
  modifier: Modifier = Modifier
) {
  val context = LocalContext.current
  val sharedPreferences = remember {
    context.getSharedPreferences("EnergyInsightPrefs", Context.MODE_PRIVATE)
  }
  
  var serverUrl by remember {
    mutableStateOf(sharedPreferences.getString("server_url", "") ?: "")
  }
  
  var tempUrl by remember {
    mutableStateOf(if (serverUrl.isEmpty()) "http://192.168.1.18:5000" else serverUrl)
  }

  if (serverUrl.isEmpty()) {
    // Connection Settings Screen
    Box(
      modifier = Modifier
        .fillMaxSize()
        .padding(24.dp),
      contentAlignment = Alignment.Center
    ) {
      Column(
        horizontalAlignment = Alignment.CenterHorizontally,
        verticalArrangement = Arrangement.spacedBy(16.dp),
        modifier = Modifier.fillMaxWidth()
      ) {
        Text(
          text = "Energy Insight",
          style = MaterialTheme.typography.headlineMedium,
          color = MaterialTheme.colorScheme.primary
        )
        Text(
          text = "Lütfen Flask sunucunuzun IP adresini ve portunu girin:",
          style = MaterialTheme.typography.bodyMedium,
          color = MaterialTheme.colorScheme.onSurfaceVariant
        )
        OutlinedTextField(
          value = tempUrl,
          onValueChange = { tempUrl = it },
          label = { Text("Sunucu Adresi") },
          modifier = Modifier.fillMaxWidth(),
          singleLine = true
        )
        Button(
          onClick = {
            if (tempUrl.isNotEmpty()) {
              sharedPreferences.edit().putString("server_url", tempUrl).apply()
              serverUrl = tempUrl
            }
          },
          modifier = Modifier.fillMaxWidth()
        ) {
          Text("Bağlan")
        }
      }
    }
  } else {
    // WebView Canvas
    Box(modifier = Modifier.fillMaxSize()) {
      AndroidView(
        factory = { ctx ->
          WebView(ctx).apply {
            settings.javaScriptEnabled = true
            settings.domStorageEnabled = true
            settings.allowFileAccess = true
            settings.allowContentAccess = true
            
            webViewClient = object : WebViewClient() {
              override fun shouldOverrideUrlLoading(view: WebView?, url: String?): Boolean {
                return false
              }
            }
            
            webChromeClient = object : WebChromeClient() {
              override fun onShowFileChooser(
                webView: WebView?,
                filePathCallback: ValueCallback<Array<Uri>>?,
                fileChooserParams: FileChooserParams?
              ): Boolean {
                MainActivity.fileChooserCallback?.invoke(filePathCallback)
                return true
              }
            }
            
            loadUrl(serverUrl)
          }
        },
        modifier = Modifier.fillMaxSize()
      )
      
      // Floating reset settings action button
      FloatingActionButton(
        onClick = {
          sharedPreferences.edit().putString("server_url", "").apply()
          serverUrl = ""
        },
        modifier = Modifier
          .align(Alignment.BottomEnd)
          .padding(16.dp)
          .padding(bottom = 60.dp),
        containerColor = MaterialTheme.colorScheme.secondaryContainer,
        contentColor = MaterialTheme.colorScheme.onSecondaryContainer
      ) {
        Text("⚙️", style = MaterialTheme.typography.titleLarge)
      }
    }
  }
}
