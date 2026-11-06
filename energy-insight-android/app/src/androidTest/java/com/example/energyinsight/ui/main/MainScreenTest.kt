package com.example.energyinsight.ui.main

import android.webkit.WebView
import androidx.activity.ComponentActivity
import androidx.compose.ui.test.junit4.createAndroidComposeRule
import androidx.test.espresso.Espresso.onView
import androidx.test.espresso.assertion.ViewAssertions.matches
import androidx.test.espresso.matcher.ViewMatchers.isAssignableFrom
import androidx.test.espresso.matcher.ViewMatchers.isDisplayed
import org.junit.Rule
import org.junit.Test

class MainScreenTest {
  @get:Rule val composeTestRule = createAndroidComposeRule<ComponentActivity>()

  @Test
  fun webView_isVisible() {
    composeTestRule.setContent { MainScreen() }
    composeTestRule.waitForIdle()
    onView(isAssignableFrom(WebView::class.java)).check(matches(isDisplayed()))
  }
}
